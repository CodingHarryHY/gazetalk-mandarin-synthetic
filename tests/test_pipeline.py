from __future__ import annotations

import io
import json
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

from gazetalk_zh.clients import GenerationError, OpenAIClient, Response
from gazetalk_zh.config import DEFAULT_BASE_URL, load_config, normalize_profile, validate_base_url
from gazetalk_zh.evaluate import audit, evaluate, near_duplicates, normalize
from gazetalk_zh.exports import check_chat, csv_text, export, render_chat
from gazetalk_zh.generate import generate, load_run, make_request, prepare
from gazetalk_zh.personas import balanced_counts, build_personas
from gazetalk_zh.planning import plan_jobs
from gazetalk_zh.provenance import append_jsonl, digest, read_jsonl, run_lock, write_jsonl
from gazetalk_zh.validation import ContractError, dialogue_schema, quality_flags, validate_dialogue


ROOT = Path(__file__).resolve().parents[1]


def fixture_dialogue(count: int = 10) -> str:
    pairs = [
        ("今天想聊聊做饭吗？", "好，我昨天做了面条。"),
        ("面条里放了什么？", "那个，绿的……小白菜。"),
        ("是小白菜，对吗？", "对，还有一个鸡蛋。"),
        ("味道怎么样？", "挺好，我和家人一起吃的。"),
        ("今天就聊到这里，谢谢你分享。", "好，下次再聊。"),
    ]
    turns = [{"speaker": speaker, "utterance": pair[index]}
             for pair in pairs for index, speaker in enumerate(("therapist", "patient"))]
    while len(turns) < count:
        index = len(turns)
        turns.append({"speaker": "therapist" if index % 2 == 0 else "patient", "utterance": "下次再聊。"})
    return json.dumps({"dialogue": turns[:count]}, ensure_ascii=False)


class FakeClient:
    def __init__(self, responses: list[object] | None = None) -> None:
        self.calls: list[dict] = []
        self.responses = list(responses or [])

    def generate(self, request: dict) -> Response:
        self.calls.append(request)
        result = self.responses.pop(0) if self.responses else fixture_dialogue()
        if isinstance(result, BaseException):
            raise result
        if not isinstance(result, str):
            raise TypeError("Fake responses must be strings or exceptions.")
        return Response(result, "offline-test-response", "offline-test-model", 100, 200)


class PipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config = load_config(ROOT / "configs/pilot.toml")
        values = {**self.config.values, "persona_count": 6, "dialogues_per_persona": 1,
                  "generation": {**self.config.values["generation"], "retry_wait_seconds": 0,
                                 "request_pause_seconds": 0, "max_attempts": 2}}
        self.config = replace(self.config, values=values, run_dir=Path(self.temp.name) / "run", api_key=None)
        self.schema = dialogue_schema(self.config.resources, 10, 40)

    def run_fake(self, fake: FakeClient, resume: bool = False) -> dict:
        with redirect_stdout(io.StringIO()):
            return generate(self.config, resume=resume, client_factory=lambda: fake)

    def test_turn_boundaries_and_odd_ending(self) -> None:
        for length in (10, 11, 40):
            self.assertEqual(len(validate_dialogue(fixture_dialogue(length), self.schema)["dialogue"]), length)
        for length in (9, 41):
            with self.assertRaises(ContractError):
                validate_dialogue(fixture_dialogue(length), self.schema)

    def test_configurable_turn_limits(self) -> None:
        schema = dialogue_schema(self.config.resources, 4, 8)
        validate_dialogue(fixture_dialogue(5), schema)
        with self.assertRaises(ContractError):
            validate_dialogue(fixture_dialogue(10), schema)

    def test_base_url_configuration_defaults_and_normalization(self) -> None:
        path = self.config_file_with_generation(base_url=None)
        self.assertEqual(load_config(path).values["generation"]["base_url"], DEFAULT_BASE_URL)
        path = self.config_file_with_generation(base_url="http://localhost:8080/proxy/v1/")
        self.assertEqual(load_config(path).values["generation"]["base_url"], "http://localhost:8080/proxy/v1")

    def config_file_with_generation(self, **overrides: Any) -> Path:
        directory = Path(self.temp.name) / "configs"
        shutil.copytree(ROOT / "configs", directory, dirs_exist_ok=True)
        path = directory / "pilot.toml"
        overrides = {"api_key": "", **overrides}
        lines = [line for line in path.read_text(encoding="utf-8").splitlines()
                 if line.partition("=")[0].strip() not in overrides]
        lines.extend(f"{key} = {json.dumps(value)}" for key, value in overrides.items() if value is not None)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    def test_configured_key_is_private_and_rotation_preserves_fingerprint(self) -> None:
        first = load_config(self.config_file_with_generation(api_key="  local-test-credential-one  "))
        self.assertEqual(first.api_key, "local-test-credential-one")
        self.assertNotIn("local-test-credential-one", repr(first))
        self.assertNotIn("api_key", first.values["generation"])
        second = load_config(self.config_file_with_generation(api_key="local-test-credential-two"))
        self.assertEqual(first.fingerprint, second.fingerprint)
        for value in (None, "", "   "):
            self.assertIsNone(load_config(self.config_file_with_generation(api_key=value)).api_key)

    def test_configured_key_precedence_and_environment_fallback(self) -> None:
        for configured, expected in (("local-test-credential", "local-test-credential"),
                                     (None, "environment-test-credential"), (" ", "environment-test-credential")):
            with patch.dict("os.environ", {"OPENAI_API_KEY": "environment-test-credential"}), \
                    patch("openai.OpenAI") as constructor:
                OpenAIClient(30, api_key=configured)
            self.assertEqual(constructor.call_args.kwargs["api_key"], expected)

    def test_configured_key_reaches_sdk_but_not_run_artifacts(self) -> None:
        key = "local-test-credential-artifact-check"
        config = replace(load_config(self.config_file_with_generation(api_key=key)),
                         values=self.config.values, run_dir=self.config.run_dir)
        mock_sdk = MagicMock()
        mock_sdk.responses.create.return_value = SimpleNamespace(
            status="completed", output=[], output_text=fixture_dialogue(),
            id="provider-response", model="gpt-6-luna", usage=None,
        )
        output = io.StringIO()
        with patch.dict("os.environ", {}, clear=True), patch("openai.OpenAI", return_value=mock_sdk) as constructor, \
                redirect_stdout(output):
            result = generate(config)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(constructor.call_args.kwargs["api_key"], key)
        self.assertNotIn("api_key", mock_sdk.responses.create.call_args.kwargs)
        self.assertNotIn(key, output.getvalue())
        for path in config.run_dir.rglob("*"):
            if path.is_file():
                self.assertNotIn(key, path.read_text(encoding="utf-8"))
        with patch("openai.OpenAI") as constructor:
            resumed = generate(replace(config, api_key="rotated-test-credential"), resume=True)
        constructor.assert_not_called()
        self.assertEqual(resumed["status"], "complete")

    def test_invalid_key_and_toml_do_not_echo_config_values(self) -> None:
        path = self.config_file_with_generation(api_key=["invalid-test-credential"])
        with self.assertRaises(ValueError) as result:
            load_config(path)
        self.assertNotIn("invalid-test-credential", str(result.exception))
        path.write_text('api_key = "unterminated-test-credential', encoding="utf-8")
        with self.assertRaises(ValueError) as result:
            load_config(path)
        self.assertNotIn("unterminated-test-credential", str(result.exception))

    def test_invalid_base_urls_fail_without_echoing_credentials(self) -> None:
        for value in ("", "example.com/v1", "ftp://example.com/v1", "https://",
                      "https://user:credential@example.com/v1", "https://example.com/v1?key=credential",
                      "https://example.com/v1#credential", " https://example.com/v1",
                      "https://example.com/\nv1", "https://example.com:bad/v1", "https://example.com:0/v1",
                      "https://[broken/v1", "https://example.com/v1/responses/",
                      "https://example.com/v1/chat/completions"):
            with self.subTest(value=value), self.assertRaises(ValueError) as result:
                validate_base_url(value)
            self.assertNotIn("user:credential", str(result.exception))
            self.assertNotIn("key=credential", str(result.exception))

    def test_custom_base_url_reaches_sdk_and_snapshot_and_blocks_changed_resume(self) -> None:
        endpoint = "https://gateway.example/v1"
        values = {**self.config.values, "generation": {**self.config.values["generation"], "base_url": endpoint}}
        config = replace(self.config, values=values)
        mock_sdk = MagicMock()
        mock_sdk.responses.create.return_value = SimpleNamespace(
            status="completed", output=[], output_text=fixture_dialogue(),
            id="provider-response", model="gpt-6-luna", usage=None,
        )
        with patch.dict("os.environ", {"OPENAI_API_KEY": "unit-test-placeholder",
                                      "OPENAI_BASE_URL": "https://ignored.example/v1"}), \
                patch("openai.OpenAI", return_value=mock_sdk) as constructor, redirect_stdout(io.StringIO()):
            result = generate(config)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(constructor.call_args.kwargs["base_url"], endpoint)
        self.assertEqual(mock_sdk.responses.create.call_count, 6)
        _, snapshot, _, _ = load_run(config.run_dir)
        self.assertEqual(snapshot["config"]["generation"]["base_url"], endpoint)
        self.assertNotIn("base_url", mock_sdk.responses.create.call_args.kwargs)
        with self.assertRaisesRegex(ValueError, "changed; use a new run_dir"):
            generate(self.config, resume=True)

    def test_strict_json_and_order(self) -> None:
        for mutate in (
            lambda p: p.update(extra="unexpected"),
            lambda p: p["dialogue"][0].update(extra="unexpected"),
            lambda p: p["dialogue"][0].update(speaker="patient"),
            lambda p: p["dialogue"][1].update(utterance="  "),
            lambda p: p["dialogue"][1].update(utterance=2),
        ):
            parsed = json.loads(fixture_dialogue())
            mutate(parsed)
            with self.assertRaises(ContractError):
                validate_dialogue(json.dumps(parsed), self.schema)
        with self.assertRaises(ContractError):
            validate_dialogue('{"dialogue": [], "dialogue": []}', self.schema)

    def test_personas_reproducible_and_provenance_complete(self) -> None:
        personas, sources = build_personas(self.config)
        self.assertEqual((personas, sources), build_personas(self.config))
        self.assertEqual(len(personas), 6)
        for persona, source in zip(personas, sources):
            self.assertEqual(set(persona), set(source["field_methods"]))
            self.assertEqual(source["persona_hash"], digest(persona))
            self.assertEqual(source["reference_status"], "not_calibrated")
            self.assertTrue(json.dumps(persona, ensure_ascii=False).isascii())

    def test_personas_jsonl_follows_schema_field_order(self) -> None:
        prepare(self.config)
        schema = json.loads(self.config.resources["schemas/persona.schema.json"])
        for line in (self.config.run_dir / "personas.jsonl").read_text(encoding="utf-8").splitlines():
            persona = json.loads(line)
            self.assertEqual(list(persona), list(schema["properties"]))
            self.assertEqual(list(persona["behaviour_profile"]),
                             list(schema["properties"]["behaviour_profile"]["properties"]))
        job = json.loads((self.config.run_dir / "jobs.jsonl").read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(list(job), sorted(job))
        load_run(self.config.run_dir)

    def test_profile_guidance_reaches_personas_and_requests(self) -> None:
        personas, _ = build_personas(self.config)
        by_profile = {persona["profile"]: persona for persona in personas}
        self.assertEqual(len(by_profile), 6)
        self.assertIn("do not add a test", by_profile["conduction"]["behaviour_profile"]["repetition"])
        self.assertIn("clarification", by_profile["wernicke"]["behaviour_profile"]["comprehension"])
        self.assertIn("written dialogue", by_profile["global"]["behaviour_profile"]["phonological_error"])
        self.assertIn("CHINESE-WANG-2021", self.config.assets["persona_rules"]["source_ids"])
        jobs = plan_jobs(self.config, personas)
        snapshot = {"config": self.config.values, "assets": self.config.assets,
                    "resources": self.config.resources}
        for job in jobs:
            persona = by_profile[job["profile"]]
            request = make_request(snapshot, persona, job)
            user_prompt = request["input"][1]["content"]
            self.assertIn(persona["behaviour_profile"]["repetition"], user_prompt)
            self.assertIn(persona["behaviour_profile"]["phonological_error"], user_prompt)

    def test_fifty_persona_quotas_and_two_thousand_jobs(self) -> None:
        config = load_config(ROOT / "configs/batch_2000.toml")
        counts = balanced_counts(50, 42)
        self.assertEqual(sorted(counts.values()), [8, 8, 8, 8, 9, 9])
        personas, _ = build_personas(config)
        jobs = plan_jobs(config, personas)
        self.assertEqual(len(jobs), 2000)
        self.assertEqual(len({j["dialogue_id"] for j in jobs}), 2000)
        self.assertEqual(jobs, plan_jobs(config, personas))
        for persona in personas:
            group = [j for j in jobs if j["persona_id"] == persona["persona_id"]]
            self.assertEqual(len(group), 40)
            self.assertEqual(len({j["session_topic"] for j in group}), 5)
            self.assertEqual(len({j["conversation_mode"] for j in group}), 2)
            self.assertEqual(len({j["therapist_strategy"] for j in group}), 5)

    def test_aliases(self) -> None:
        self.assertEqual(normalize_profile("anomia"), "anomic")
        self.assertEqual(normalize_profile("TCmotor"), "tcmotor")
        with self.assertRaises(ValueError):
            normalize_profile("unknown")

    def test_prompt_request_preserves_chinese_examples_and_session(self) -> None:
        prepare(self.config)
        _, snapshot, personas, jobs = load_run(self.config.run_dir)
        persona = next(p for p in personas if p["persona_id"] == jobs[0]["persona_id"])
        request = make_request(snapshot, persona, jobs[0])
        system = request["input"][0]["content"]
        user = request["input"][1]["content"]
        self.assertEqual(system, self.config.resources["prompts/system.txt"])
        self.assertIn("是长凳吗？", system)
        self.assertIn("慢慢想。", system)
        self.assertIn(json.dumps(persona, ensure_ascii=False, indent=2), user)
        self.assertNotIn("{persona}", user)
        self.assertNotIn("{session}", user)
        self.assertIn('"dialogue_id": "' + jobs[0]["dialogue_id"] + '"', user)
        self.assertEqual(json.loads(json.dumps(request, ensure_ascii=False)), request)
        self.assertIn("Simplified Chinese", request["input"][0]["content"])
        self.assertFalse(request["store"])
        self.assertEqual(request["model"], self.config.values["generation"]["model"])
        self.assertNotIn("temperature", request)

    def test_retry_rejects_invalid_response_and_records_attempts(self) -> None:
        fake = FakeClient(["invalid JSON"])
        result = self.run_fake(fake)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(len(fake.calls), 7)
        events = read_jsonl(self.config.run_dir / "attempts.jsonl")
        self.assertEqual(sum(e["status"] == "rejected" for e in events), 1)
        self.assertIn("earlier attempt", fake.calls[1]["input"][1]["content"])
        report = audit(self.config.run_dir)
        self.assertTrue(report["complete"])
        self.assertEqual(report["valid_records"], 6)

    def test_token_truncation_retries_whole_dialogue_with_bounded_budget(self) -> None:
        response = Response('{"dialogue": [', "truncated", "offline-test-model", 50, 8192)
        fake = FakeClient([GenerationError("output_token_limit", response=response)])
        self.run_fake(fake)
        self.assertEqual(fake.calls[1]["max_output_tokens"], 2 * fake.calls[0]["max_output_tokens"])
        self.assertEqual(len(read_jsonl(self.config.run_dir / "dialogues.jsonl")), 6)
        summary = evaluate(self.config.run_dir)
        self.assertEqual(summary["reported_request_token_usage"]["output_tokens"], 8192 + 1200)

    def test_resume_does_not_call_api_again(self) -> None:
        self.run_fake(FakeClient())
        fake = FakeClient()
        self.run_fake(fake, resume=True)
        self.assertEqual(fake.calls, [])
        with self.assertRaises(ValueError):
            self.run_fake(fake)

    def test_interrupted_run_recovers_missing_jobs(self) -> None:
        with self.assertRaises(KeyboardInterrupt):
            self.run_fake(FakeClient([fixture_dialogue(), KeyboardInterrupt()]))
        self.assertEqual(len(read_jsonl(self.config.run_dir / "dialogues.jsonl")), 1)
        fake = FakeClient()
        result = self.run_fake(fake, resume=True)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(len(fake.calls), 5)

    def test_cached_response_recovers_uncommitted_success(self) -> None:
        self.run_fake(FakeClient())
        path = self.config.run_dir / "dialogues.jsonl"
        rows = read_jsonl(path)
        write_jsonl(path, rows[:-1])
        fake = FakeClient()
        self.run_fake(fake, resume=True)
        self.assertEqual(fake.calls, [])
        last = read_jsonl(path)[-1]
        self.assertTrue(last["cached"])
        self.assertEqual(last["input_tokens"], 0)

    def test_config_drift_blocks_resume(self) -> None:
        prepare(self.config)
        changed = replace(self.config, values={**self.config.values, "seed": 9})
        with self.assertRaises(ValueError):
            prepare(changed)

    def test_resource_metadata_does_not_change_prompt_snapshot(self) -> None:
        package = Path(self.temp.name) / "package"
        shutil.copytree(ROOT / "src/gazetalk_zh", package,
                        ignore=shutil.ignore_patterns(".DS_Store", "__pycache__"))
        with patch("gazetalk_zh.config.PACKAGE", package):
            clean = load_config(ROOT / "configs/pilot_six_rules.toml")
            (package / "resources/.DS_Store").write_bytes(b"\xff\xfe\x00Finder metadata")
            with_metadata = load_config(ROOT / "configs/pilot_six_rules.toml")
        self.assertEqual(clean.resources, with_metadata.resources)
        self.assertEqual(clean.fingerprint, with_metadata.fingerprint)
        self.assertNotIn(".DS_Store", with_metadata.resources)

    def test_prompt_change_blocks_resume_before_api_and_preserves_snapshot(self) -> None:
        prepare(self.config)
        snapshot_path = self.config.run_dir / "snapshot.json"
        original = snapshot_path.read_bytes()
        for name in ("prompts/system.txt", "prompts/session.txt"):
            with self.subTest(resource=name):
                resources = {**self.config.resources, name: self.config.resources[name] + "\nChanged instruction.\n"}
                changed = replace(self.config, resources=resources)
                self.assertNotEqual(changed.fingerprint, self.config.fingerprint)
                with patch("gazetalk_zh.generate.OpenAIClient") as client:
                    with self.assertRaisesRegex(ValueError, "use a new run_dir"):
                        generate(changed, resume=True)
                client.assert_not_called()
                self.assertEqual(snapshot_path.read_bytes(), original)
                load_run(self.config.run_dir)

    def test_invalid_existing_output_and_partial_tail_are_not_skipped(self) -> None:
        self.run_fake(FakeClient())
        path = self.config.run_dir / "dialogues.jsonl"
        original = path.read_text()
        path.write_text(original + '{"dialogue_id":')
        with self.assertRaises(ValueError):
            self.run_fake(FakeClient(), resume=True)
        path.write_text(original)
        rows = read_jsonl(path)
        rows[0]["text"] = fixture_dialogue(9)
        write_jsonl(path, rows)
        self.assertEqual(audit(self.config.run_dir)["structural_status"], "fail")
        with self.assertRaises(ValueError):
            self.run_fake(FakeClient(), resume=True)

    def test_tampering_and_duplicate_ids(self) -> None:
        self.run_fake(FakeClient())
        path = self.config.run_dir / "dialogues.jsonl"
        rows = read_jsonl(path)
        append_jsonl(path, rows[0])
        with self.assertRaises(ValueError):
            self.run_fake(FakeClient(), resume=True)
        rows[0]["latency_local"] += 1
        write_jsonl(path, rows)
        with self.assertRaises(ValueError):
            self.run_fake(FakeClient(), resume=True)

    def test_input_file_drift_is_detected(self) -> None:
        prepare(self.config)
        path = self.config.run_dir / "personas.jsonl"
        rows = read_jsonl(path)
        rows[0]["severity"] = "severe"
        write_jsonl(path, rows)
        with self.assertRaises(ValueError):
            load_run(self.config.run_dir)

    def test_fatal_error_stops_without_logging_secrets(self) -> None:
        fake = FakeClient([GenerationError("http_401", fatal=True)])
        with self.assertRaises(GenerationError):
            self.run_fake(fake)
        self.assertEqual(len(fake.calls), 1)
        self.assertEqual(read_jsonl(self.config.run_dir / "dialogues.jsonl"), [])
        manifest, _, _, _ = load_run(self.config.run_dir)
        self.assertEqual(manifest["status"], "blocked")

    def test_missing_key_is_not_a_synthetic_result(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(GenerationError):
                OpenAIClient(30)

    def test_openai_adapter_reads_structured_text_and_usage(self) -> None:
        mock_sdk = MagicMock()
        mock_sdk.responses.create.return_value = SimpleNamespace(
            status="completed", output=[], output_text=fixture_dialogue(),
            id="provider-response", model="gpt-6-luna",
            usage=SimpleNamespace(input_tokens=120, output_tokens=240),
        )
        with patch.dict("os.environ", {"OPENAI_API_KEY": "unit-test-placeholder"}), patch("openai.OpenAI", return_value=mock_sdk) as constructor:
            result = OpenAIClient(30).generate({"model": "gpt-6-luna", "store": False})
        self.assertEqual(constructor.call_args.kwargs["base_url"], DEFAULT_BASE_URL)
        self.assertEqual(result.input_tokens, 120)
        self.assertEqual(result.output_tokens, 240)
        self.assertEqual(result.text, fixture_dialogue())
        mock_sdk.responses.create.assert_called_once_with(model="gpt-6-luna", store=False)

    def test_openai_adapter_logs_api_error_without_secrets_or_prompt(self) -> None:
        import httpx2
        from openai import BadRequestError

        secret = "unit-test-secret-key"
        response = httpx2.Response(
            400, json={"error": {"type": "invalid_request_error", "param": "text.format.schema",
                                 "message": f"Invalid schema; key={secret}"}},
            request=httpx2.Request("POST", "https://example.test/v1/responses"),
            headers={"x-request-id": "test-request-id"},
        )
        mock_sdk = MagicMock()
        mock_sdk.responses.create.side_effect = BadRequestError("Invalid schema", response=response,
                                                                 body=response.json())
        output = io.StringIO()
        with patch("openai.OpenAI", return_value=mock_sdk), redirect_stderr(output):
            with self.assertRaises(GenerationError):
                OpenAIClient(30, api_key=secret).generate({"model": "gpt-6.1-sol", "input": [
                    {"role": "user", "content": "private prompt text"}]})
        request_log, response_log = (json.loads(line) for line in output.getvalue().splitlines())
        self.assertEqual(request_log["parameters"]["model"], "gpt-6.1-sol")
        self.assertEqual(response_log["status_code"], 400)
        self.assertEqual(response_log["error"]["param"], "text.format.schema")
        self.assertNotIn(secret, output.getvalue())
        self.assertNotIn("private prompt text", output.getvalue())

    def test_openai_adapter_preserves_truncated_usage(self) -> None:
        mock_sdk = MagicMock()
        mock_sdk.responses.create.return_value = SimpleNamespace(
            status="incomplete", output=[], output_text="{", id="provider-response", model="gpt-6-luna",
            incomplete_details=SimpleNamespace(reason="max_output_tokens"),
            usage=SimpleNamespace(input_tokens=120, output_tokens=240),
        )
        with patch.dict("os.environ", {"OPENAI_API_KEY": "unit-test-placeholder"}), patch("openai.OpenAI", return_value=mock_sdk):
            with self.assertRaises(GenerationError) as result:
                OpenAIClient(30).generate({"model": "gpt-6-luna"})
        self.assertEqual(result.exception.code, "output_token_limit")
        assert result.exception.response is not None
        self.assertEqual(result.exception.response.output_tokens, 240)

    def test_failed_jobs_can_be_retried(self) -> None:
        fake = FakeClient([GenerationError("connection_or_timeout"), GenerationError("connection_or_timeout")])
        result = self.run_fake(fake)
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(len(read_jsonl(self.config.run_dir / "errors.jsonl")), 1)
        retry = FakeClient()
        self.run_fake(retry, resume=True)
        self.assertEqual(len(retry.calls), 1)

    def test_lock_prevents_concurrent_writes(self) -> None:
        with run_lock(self.config.run_dir):
            with self.assertRaises(ValueError):
                with run_lock(self.config.run_dir):
                    self.fail("A second lock must not be acquired.")

    def test_chinese_metrics_and_duplicate_detection(self) -> None:
        self.assertNotEqual(normalize("今天吃面。"), normalize("今天吃饭。"))
        self.assertEqual(normalize("今天，吃面！"), normalize("今天吃面"))
        self.run_fake(FakeClient())
        summary = evaluate(self.config.run_dir)
        self.assertEqual(summary["normalized_complete_dialogue_duplicate_extras"], 5)
        self.assertEqual(summary["reported_request_token_usage"], {"input_tokens": 600, "output_tokens": 1200})
        self.assertGreater(next(iter(summary["groups"]["profile"].values()))["mean_patient_han_characters_per_turn"], 0)
        text = "今天我们一起去公园散步看见很多花和树又一起回家吃晚饭聊天" * 2
        pairs = near_duplicates([text, text + "了"], ["A", "B"])
        self.assertEqual(pairs["pairs"], 1)

    def test_exports_preserve_turn_map_and_review_edits(self) -> None:
        self.run_fake(FakeClient())
        result = export(self.config.run_dir)
        target = Path(result["directory"])
        self.assertEqual(len(list((target / "chat").glob("*.cha"))), 6)
        mapping = read_jsonl(target / "chat" / "turn_map.jsonl")
        self.assertEqual(len(mapping), 60)
        for item in mapping:
            self.assertTrue(item["main_tier_indices"])
            self.assertTrue(item["source_utterance"])
        review = target / "review" / "dialogues.csv"
        review.write_text("User review must survive re-export.")
        self.assertEqual(export(self.config.run_dir)["status"], "already_exported")
        self.assertEqual(review.read_text(), "User review must survive re-export.")
        self.assertEqual(result["external_chat_validation"], "not_run")

    def test_chat_sentence_mapping_and_reserved_characters(self) -> None:
        self.run_fake(FakeClient())
        row = read_jsonl(self.config.run_dir / "dialogues.jsonl")[0]
        parsed = json.loads(row["text"])
        parsed["dialogue"][0]["utterance"] = "你好。今天好吗？"
        parsed["dialogue"][1]["utterance"] = "[嗯]，好……"
        row["text"] = json.dumps(parsed)
        text, mapping = render_chat(row)
        self.assertEqual(mapping[0]["main_tier_indices"], [1, 2])
        self.assertEqual(check_chat(text), 11)
        self.assertNotIn("[嗯]", text)
        self.assertEqual(mapping[1]["source_utterance"], "[嗯]，好……")

    def test_csv_formula_escaping(self) -> None:
        self.assertIn("'=1+1", csv_text([{"value": "=1+1"}], ["value"]))

    def test_quality_flags_are_not_clinical_labels(self) -> None:
        parsed = json.loads(fixture_dialogue())
        parsed["dialogue"][-1]["utterance"] = "然后呢？"
        self.assertIn("closing_question_requires_review", quality_flags(parsed["dialogue"]))


if __name__ == "__main__":
    unittest.main()
