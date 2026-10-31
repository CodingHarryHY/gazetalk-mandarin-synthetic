from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from gazetalk_zh.dialogue_to_samples import SYSTEM_PROMPT, convert, dialogue_samples, main


def record(*turns: tuple[str, str]) -> dict:
    return {"dialogue_id": "example", "text": json.dumps({"dialogue": [
        {"speaker": speaker, "utterance": text} for speaker, text in turns
    ]}, ensure_ascii=False)}


class DialogueToSamplesTests(unittest.TestCase):
    def test_prefixes_and_single_targets(self) -> None:
        samples = dialogue_samples(record(
            ("therapist", "你想喝什么？"), ("patient", "咖啡……白色那个。"),
            ("therapist", "你是说牛奶吗？"), ("patient", "对。"),
            ("therapist", "好的。"), ("patient", "谢谢。"),
        ))
        self.assertEqual(len(samples), 2)
        self.assertEqual(samples[0], {
            "prompt": [{"role": "system", "content": SYSTEM_PROMPT},
                       {"role": "assistant", "content": "你想喝什么？"},
                       {"role": "user", "content": "咖啡……白色那个。"}],
            "completion": [{"role": "assistant", "content": "你是说牛奶吗？"}],
        })
        self.assertEqual(samples[1]["prompt"], samples[0]["prompt"] + samples[0]["completion"] +
                         [{"role": "user", "content": "对。"}])
        self.assertEqual(samples[1]["completion"], [{"role": "assistant", "content": "好的。"}])

    def test_patient_opening_and_original_whitespace(self) -> None:
        samples = dialogue_samples(record(("patient", " 嗯…… "), ("therapist", "请慢慢说。")))
        self.assertEqual(len(samples), 1)
        self.assertEqual(samples[0]["prompt"][-1]["content"], " 嗯…… ")
        self.assertEqual(dialogue_samples(record(("therapist", "你好。"))), [])

    def test_invalid_records(self) -> None:
        for bad in [None, {}, {"text": "invalid"}, {"text": "[]"}, record(),
                    record(("unknown", "你好")), record(("patient", "  ")),
                    {"text": '{"dialogue": [null]}'},
                    {"text": '{"dialogue": [{"speaker": [], "utterance": "x"}]}'}]:
            with self.subTest(record=bad), self.assertRaises(ValueError):
                dialogue_samples(bad)

    def test_file_conversion_and_cli_summary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source, target = Path(directory) / "input.jsonl", Path(directory) / "output.jsonl"
            row = record(("patient", "你好。"), ("therapist", "你好！"))
            source.write_text((json.dumps(row, ensure_ascii=False) + "\n") * 2, encoding="utf-8")
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                self.assertEqual(main(["--input", str(source), "--output", str(target)]), 0)
            self.assertIn("Read 2 dialogues; wrote 2 samples", stdout.getvalue())
            lines = target.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 2)
            self.assertIn("你好！", lines[0])
            self.assertEqual(json.loads(lines[0]), dialogue_samples(row)[0])
            with self.assertRaises(FileExistsError):
                convert(source, target)
            with self.assertRaises(ValueError):
                convert(source, source)

    def test_error_line_and_no_partial_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source, target = Path(directory) / "input.jsonl", Path(directory) / "output.jsonl"
            valid = json.dumps(record(("patient", "你好。"), ("therapist", "你好！")))
            for bad in ["invalid", json.dumps(record(("patient", ""))), ""]:
                with self.subTest(bad=bad):
                    source.write_text(valid + "\n" + bad + "\n", encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, "Input line 2:"):
                        convert(source, target)
                    self.assertFalse(target.exists())
