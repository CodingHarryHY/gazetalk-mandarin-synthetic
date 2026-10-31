from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from statistics import fmean
from typing import Any

from .generate import checked_records, load_run
from .provenance import digest, now, read_jsonl, run_lock, write_json, write_jsonl
from .validation import quality_flags


HAN = re.compile(r"[\u3400-\u9fff]")
FILLERS = re.compile(r"[嗯呃]")


def normalize(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKC", text).casefold() if c.isalnum())


def duplicate_extras(values: list[str]) -> int:
    return sum(count - 1 for count in Counter(values).values())


def near_duplicates(texts: list[str], ids: list[str], threshold: float = 0.85) -> dict[str, Any]:
    postings: dict[str, list[int]] = defaultdict(list)
    sizes: list[int] = []
    examples = []
    total = 0
    for index, text in enumerate(texts):
        shingles = {text[i:i + 5] for i in range(max(0, len(text) - 4))}
        sizes.append(len(shingles))
        overlaps: Counter[int] = Counter()
        if len(text) >= 20:
            for shingle in shingles:
                overlaps.update(postings[shingle])
            for other, overlap in overlaps.items():
                union = len(shingles) + sizes[other] - overlap
                if text != texts[other] and union and overlap / union >= threshold:
                    total += 1
                    if len(examples) < 200:
                        examples.append({"dialogue_ids": [ids[other], ids[index]],
                                         "character_5gram_jaccard": round(overlap / union, 4)})
            for shingle in shingles:
                postings[shingle].append(index)
    return {"pairs": total, "threshold": threshold, "examples": examples,
            "examples_truncated": total > len(examples), "minimum_normalized_characters": 20,
            "note": "Descriptive heuristic; short responses are excluded and exact matches are reported separately."}


def audit(run: Path) -> dict[str, Any]:
    with run_lock(run):
        manifest, snapshot, _, jobs = load_run(run)
        try:
            rows = checked_records(run, snapshot, jobs)
        except ValueError as exc:
            report = {"time": now(), "structural_status": "fail", "error": str(exc),
                      "clinical_status": "not_evaluated"}
            write_json(run / "validation.json", report)
            return report
        flags = [{"dialogue_id": row["dialogue_id"], "flags": quality_flags(json.loads(row["text"])["dialogue"]),
                  "human_review_status": "not_reviewed"} for row in rows]
        report = {"time": now(), "structural_status": "pass", "valid_records": len(rows),
                  "planned_records": len(jobs), "missing_records": len(jobs) - len(rows),
                  "complete": len(rows) == len(jobs), "run_status": manifest["status"],
                  "output_hash": digest(rows), "records_with_quality_flags": sum(bool(r["flags"]) for r in flags),
                  "clinical_status": "not_evaluated", "semantic_completion_status": "not_verified",
                  "note": "Structural validity does not establish conversational completion or clinical realism."}
        write_json(run / "validation.json", report)
        write_jsonl(run / "quality_flags.jsonl", flags)
        return report


def evaluate(run: Path) -> dict[str, Any]:
    with run_lock(run):
        _, snapshot, personas, jobs = load_run(run)
        rows = checked_records(run, snapshot, jobs)
        by_persona = {p["persona_id"]: p for p in personas}
        by_job = {j["dialogue_id"]: j for j in jobs}
        metrics, patients, complete_texts, literal_texts = [], [], [], []
        per_persona: dict[str, list[str]] = defaultdict(list)
        for row in rows:
            turns = json.loads(row["text"])["dialogue"]
            patient = [t["utterance"] for t in turns if t["speaker"] == "patient"]
            therapist = [t["utterance"] for t in turns if t["speaker"] == "therapist"]
            patient_text = " ".join(patient)
            patient_key = normalize(patient_text)
            patients.append(patient_key)
            complete_texts.append("|".join(t["speaker"] + ":" + normalize(t["utterance"]) for t in turns))
            literal_texts.append(json.dumps(turns, ensure_ascii=False, sort_keys=True))
            per_persona[row["persona_id"]].append(patient_key)
            metrics.append({
                "dialogue_id": row["dialogue_id"], "profile": row["profile"],
                "severity": by_persona[row["persona_id"]]["severity"],
                "topic": row["session_topic"], "mode": by_job[row["dialogue_id"]]["conversation_mode"],
                "turn_count": len(turns), "patient_turns": len(patient),
                "patient_han_characters": len(HAN.findall(patient_text)),
                "mean_patient_han_characters_per_turn": fmean(len(HAN.findall(t)) for t in patient),
                "mean_therapist_han_characters_per_turn": fmean(len(HAN.findall(t)) for t in therapist),
                "filler_character_occurrences": len(FILLERS.findall(patient_text)),
                "ellipsis_marker_occurrences": len(re.findall(r"…+|\.{3,}", patient_text)),
                "repeated_patient_turn_extras": duplicate_extras([normalize(t) for t in patient]),
                "quality_flags": quality_flags(turns),
            })
        grouped = {}
        for dimension in ("profile", "severity", "topic", "mode"):
            groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for row in metrics:
                groups[row[dimension]].append(row)
            grouped[dimension] = {key: {"records": len(group), "mean_turns": fmean(r["turn_count"] for r in group),
                                        "mean_patient_han_characters_per_turn": fmean(r["mean_patient_han_characters_per_turn"] for r in group)}
                                  for key, group in sorted(groups.items())}
        usage = Counter()
        unknown_usage = 0
        events = read_jsonl(run / "attempts.jsonl")
        starts = {event["attempt_id"] for event in events if event.get("status") == "started"}
        outcomes = {event["attempt_id"] for event in events if event.get("status") in ("validated", "rejected")}
        for event in events:
            if event.get("status") in ("validated", "rejected") and not event["cached"]:
                response = event.get("response")
                if isinstance(response, dict) and response.get("input_tokens") is not None and response.get("output_tokens") is not None:
                    usage["input_tokens"] += response["input_tokens"]
                    usage["output_tokens"] += response["output_tokens"]
                else:
                    unknown_usage += 1
        summary = {
            "time": now(), "records": len(rows), "planned_records": len(jobs), "output_hash": digest(rows),
            "turn_count_histogram": dict(sorted(Counter(str(m["turn_count"]) for m in metrics).items())),
            "literal_complete_dialogue_duplicate_extras": duplicate_extras(literal_texts),
            "normalized_complete_dialogue_duplicate_extras": duplicate_extras(complete_texts),
            "normalized_patient_text_duplicate_extras": duplicate_extras(patients),
            "within_persona_patient_duplicate_extras": sum(duplicate_extras(v) for v in per_persona.values()),
            "patient_near_duplicates": near_duplicates(patients, [r["dialogue_id"] for r in rows]),
            "groups": grouped, "reported_request_token_usage": dict(usage),
            "request_outcomes_without_token_usage": unknown_usage,
            "attempts_without_recorded_outcome": len(starts - outcomes),
            "notes": ["Han character counts are not word counts or clinical MLU.",
                      "Filler and ellipsis counts are textual proxies, not acoustic or clinical annotations.",
                      "No real-corpus comparison, clinical validation, or training utility evaluation was performed.",
                      "Natural closure, Simplified Chinese usage, and support appropriateness require review."],
        }
        write_json(run / "evaluation" / "summary.json", summary)
        write_jsonl(run / "evaluation" / "record_metrics.jsonl", metrics)
        return summary
