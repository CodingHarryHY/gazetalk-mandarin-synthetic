from __future__ import annotations

import json
import platform
import time
import uuid
from collections import Counter
from pathlib import Path
from importlib.metadata import version
from typing import Any, Callable

from . import __version__
from .clients import Client, GenerationError, OpenAIClient, Response
from .config import Config
from .personas import build_personas
from .planning import plan_jobs
from .prompts import build_prompt
from .provenance import (append_jsonl, canonical, digest, index_unique, load_json,
                         now, read_jsonl, run_lock, write_json, write_jsonl)
from .validation import ContractError, dialogue_schema, quality_flags, validate_dialogue, validate_record


def _snapshot(config: Config) -> dict[str, Any]:
    return {"config": config.values, "assets": config.assets,
            "resources": config.resources, "source": config.source}


def prepare(config: Config) -> dict[str, Any]:
    run = config.run_dir
    with run_lock(run):
        if (run / "manifest.json").exists():
            manifest, _, _, _ = load_run(run)
            if manifest["fingerprint"] != config.fingerprint:
                raise ValueError("Run configuration, catalogs, prompts, schema, or code changed; use a new run_dir.")
            return manifest
        if any(path.name != ".lock" for path in run.iterdir()):
            raise ValueError("Run directory has files but no manifest; preserve it and use a new run_dir.")
        personas, sources = build_personas(config)
        jobs = plan_jobs(config, personas)
        snapshot = _snapshot(config)
        persona_fields = json.loads(config.resources["schemas/persona.schema.json"])["properties"]
        behaviour_fields = persona_fields["behaviour_profile"]["properties"]
        ordered_personas = []
        for persona in personas:
            ordered = {field: persona[field] for field in persona_fields}
            ordered["behaviour_profile"] = {field: persona["behaviour_profile"][field]
                                            for field in behaviour_fields}
            ordered_personas.append(ordered)
        write_json(run / "snapshot.json", snapshot)
        write_jsonl(run / "personas.jsonl", ordered_personas, sort_keys=False)
        write_jsonl(run / "persona_provenance.jsonl", sources)
        write_jsonl(run / "jobs.jsonl", jobs)
        manifest = {
            "run_id": run.name, "created_at": now(), "updated_at": now(),
            "pipeline_version": __version__, "fingerprint": config.fingerprint,
            "runtime": {"python": platform.python_version(), "openai": version("openai"),
                        "jsonschema": version("jsonschema")},
            "input_hashes": {"personas.jsonl": digest(personas), "persona_provenance.jsonl": digest(sources),
                             "jobs.jsonl": digest(jobs)},
            "status": "prepared", "planned_dialogues": len(jobs), "persona_count": len(personas),
            "profile_persona_counts": dict(Counter(p["profile"] for p in personas)),
            "profile_dialogue_counts": dict(Counter(j["profile"] for j in jobs)),
            "reference_status": "not_calibrated", "clinical_validation": "not_performed",
            "publication_permission": "not_determined", "training_permission": "not_determined",
            "data_statement": "Fictional rule-based personas; no restricted transcripts were ingested.",
            "language_policy": "English auxiliary information; Simplified Chinese dialogue content.",
        }
        write_json(run / "manifest.json", manifest)
        return manifest


def load_run(run: Path) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    manifest = load_json(run / "manifest.json")
    snapshot = load_json(run / "snapshot.json")
    if digest(snapshot) != manifest["fingerprint"]:
        raise ValueError("Run snapshot integrity check failed.")
    inputs = {}
    for name, expected in manifest["input_hashes"].items():
        rows = read_jsonl(run / name)
        if digest(rows) != expected:
            raise ValueError(f"Run input integrity check failed: {name}.")
        inputs[name] = rows
    index_unique(inputs["personas.jsonl"], "persona_id")
    index_unique(inputs["jobs.jsonl"], "dialogue_id")
    return manifest, snapshot, inputs["personas.jsonl"], inputs["jobs.jsonl"]


def checked_records(run: Path, snapshot: dict[str, Any], jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = read_jsonl(run / "dialogues.jsonl")
    index_unique(rows, "dialogue_id")
    by_id = index_unique(jobs, "dialogue_id")
    receipts = {}
    for event in read_jsonl(run / "attempts.jsonl"):
        if event.get("status") == "validated":
            receipts.setdefault(event["dialogue_id"], set()).add(event["record_hash"])
    for row in rows:
        job = by_id.get(row["dialogue_id"])
        if job is None:
            raise ValueError("Output contains an unplanned dialogue ID.")
        validate_record(row, job, snapshot["config"], snapshot["resources"])
        if digest(row) not in receipts.get(row["dialogue_id"], set()):
            raise ValueError("Output is missing a matching validated attempt receipt.")
    return rows


def make_request(snapshot: dict[str, Any], persona: dict[str, Any], job: dict[str, Any],
                 feedback: str | None = None) -> dict[str, Any]:
    settings = snapshot["config"]
    system, user = build_prompt(persona, job, snapshot["assets"], snapshot["resources"])
    if feedback:
        user += "\nAn earlier attempt failed validation: " + feedback + "\nReturn a fresh complete dialogue."
    request = {
        "model": settings["generation"]["model"], "store": False,
        "reasoning": {"effort": settings["generation"]["reasoning_effort"]},
        "max_output_tokens": settings["generation"]["max_output_tokens"],
        "input": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "text": {"format": {"type": "json_schema", "name": "mandarin_dialogue_v01", "strict": True,
                            "schema": dialogue_schema(snapshot["resources"], settings["min_turns"], settings["max_turns"])}},
    }
    if "service_tier" in settings["generation"]:
        request["service_tier"] = settings["generation"]["service_tier"]
    return request


def generate(config: Config, *, resume: bool = False,
             client_factory: Callable[[], Client] | None = None) -> dict[str, Any]:
    prepare(config)
    run = config.run_dir
    with run_lock(run):
        manifest, snapshot, personas, jobs = load_run(run)
        completed = checked_records(run, snapshot, jobs)
        if completed and not resume:
            raise ValueError("Output already exists; use --resume. Overwrite is not supported.")
        done_ids = {row["dialogue_id"] for row in completed}
        pending = [job for job in jobs if job["dialogue_id"] not in done_ids]
        if not pending:
            manifest.update(status="complete", completed_dialogues=len(completed), updated_at=now())
            write_json(run / "manifest.json", manifest)
            return manifest
        settings = config.values["generation"]
        try:
            client = client_factory() if client_factory else OpenAIClient(
                settings["timeout_seconds"], base_url=settings["base_url"], api_key=config.api_key)
        except GenerationError as exc:
            manifest.update(status="blocked", blocked_reason=exc.code, updated_at=now())
            write_json(run / "manifest.json", manifest)
            raise
        cache = {}
        for entry in read_jsonl(run / "cache.jsonl"):
            if digest(entry["request"]) != entry["key"] or digest(entry["response"]) != entry["response_hash"]:
                raise ValueError("Cache integrity check failed.")
            cache[entry["key"]] = entry["response"]
        counts = Counter(event["dialogue_id"] for event in read_jsonl(run / "attempts.jsonl")
                         if event.get("status") == "started")
        by_persona = index_unique(personas, "persona_id")
        manifest.update(status="running", blocked_reason=None, updated_at=now())
        write_json(run / "manifest.json", manifest)
        failures = 0
        try:
            for job in pending:
                feedback = None
                token_limit = settings["max_output_tokens"]
                success = False
                for local_attempt in range(settings["max_attempts"]):
                    counts[job["dialogue_id"]] += 1
                    attempt = counts[job["dialogue_id"]]
                    request = make_request(snapshot, by_persona[job["persona_id"]], job, feedback)
                    request["max_output_tokens"] = token_limit
                    key = digest(request)
                    cached = key in cache and local_attempt == 0
                    event_id = str(uuid.uuid4())
                    base = {"attempt_id": event_id, "dialogue_id": job["dialogue_id"], "attempt": attempt,
                            "request_hash": key, "cached": cached}
                    append_jsonl(run / "attempts.jsonl", {**base, "status": "started", "time": now(),
                                  "request": request, "persona_hash": digest(by_persona[job["persona_id"]])})
                    started = time.monotonic()
                    response = None
                    try:
                        response = Response(**cache[key]) if cached else client.generate(request)
                        parsed = validate_dialogue(response.text, request["text"]["format"]["schema"])
                        row = {key: job[key] for key in ("persona_id", "dialogue_id", "profile", "session_index",
                                                        "session_topic", "therapist_strategy")}
                        row.update(backend=settings["backend"], model=settings["model"], cached=cached,
                                   input_tokens=0 if cached else response.input_tokens,
                                   output_tokens=0 if cached else response.output_tokens,
                                   attempt=attempt, latency_local=time.monotonic() - started, text=canonical(parsed))
                        validate_record(row, job, config.values, config.resources)
                    except (ContractError, GenerationError) as exc:
                        feedback = str(exc)
                        if isinstance(exc, GenerationError) and exc.code == "output_token_limit":
                            token_limit = settings["max_output_tokens"] * 2
                        failed_response = response or getattr(exc, "response", None)
                        append_jsonl(run / "attempts.jsonl", {**base, "status": "rejected", "time": now(),
                                      "error": feedback, "response": failed_response.to_dict() if failed_response else None})
                        if isinstance(exc, GenerationError) and exc.fatal:
                            append_jsonl(run / "errors.jsonl", {**base, "time": now(), "error": feedback, "fatal": True})
                            manifest.update(status="blocked", blocked_reason=feedback)
                            raise
                        if local_attempt + 1 < settings["max_attempts"]:
                            time.sleep(settings["retry_wait_seconds"] * 2 ** local_attempt)
                        continue
                    if not cached:
                        entry = {"key": key, "request": request, "response": response.to_dict(),
                                 "response_hash": digest(response.to_dict())}
                        append_jsonl(run / "cache.jsonl", entry)
                        cache[key] = entry["response"]
                    append_jsonl(run / "attempts.jsonl", {**base, "status": "validated", "time": now(),
                                  "record_hash": digest(row), "response": response.to_dict(),
                                  "quality_flags": quality_flags(parsed["dialogue"])})
                    append_jsonl(run / "dialogues.jsonl", row)
                    done_ids.add(job["dialogue_id"])
                    success = True
                    break
                if not success:
                    failures += 1
                    append_jsonl(run / "errors.jsonl", {"dialogue_id": job["dialogue_id"], "time": now(),
                                  "error": feedback, "fatal": False, "attempts_total": counts[job["dialogue_id"]]})
                print(json.dumps({"completed": len(done_ids), "planned": len(jobs), "failed_this_invocation": failures}))
                if settings["request_pause_seconds"]:
                    time.sleep(settings["request_pause_seconds"])
            manifest["status"] = "complete" if len(done_ids) == len(jobs) else "incomplete"
        except BaseException:
            if manifest["status"] == "running":
                manifest["status"] = "interrupted"
            raise
        finally:
            manifest.update(completed_dialogues=len(done_ids), failed_this_invocation=failures, updated_at=now())
            write_json(run / "manifest.json", manifest)
        return manifest
