from __future__ import annotations

from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from gazetalk_zh.provenance import read_jsonl, write_jsonl
from gazetalk_zh.split_dialogues import partition, split_records


def records(count: int = 200) -> list[dict]:
    return [{"dialogue_id": f"{profile}-{i:04d}", "persona_id": f"{profile}-p{i % 10}",
             "profile": profile, "extra_metadata": {"keep": True},
             "text": json.dumps({"dialogue": [
                 {"speaker": "therapist", "utterance": "今天想聊什么？"},
                 {"speaker": "patient", "utterance": f"{profile} {i} 聊喝茶。"}]}, ensure_ascii=False)}
            for profile in ("anomic", "broca", "conduction", "global", "tcmotor", "wernicke")
            for i in range(count)]


class SplitDialogueTests(unittest.TestCase):
    def test_counts_disjointness_and_original_records(self):
        rows = records()
        original = deepcopy(rows)
        result = split_records(rows)
        self.assertEqual(rows, original)
        self.assertEqual([len(group) for group in result.values()], [960, 120, 120])
        for name, expected in (("train", 160), ("validation", 20), ("test", 20)):
            self.assertEqual(set(Counter(row["profile"] for row in result[name]).values()), {expected})
        combined = [row for group in result.values() for row in group]
        self.assertEqual(len({row["dialogue_id"] for row in combined}), 1200)
        self.assertEqual(sorted(combined, key=lambda r: r["dialogue_id"]),
                         sorted(rows, key=lambda r: r["dialogue_id"]))

    def test_seed_and_input_order(self):
        rows = records(20)
        self.assertEqual(split_records(rows), split_records(list(reversed(rows))))
        self.assertNotEqual(split_records(rows, 42), split_records(rows, 43))

    def test_rounding_keeps_every_dialogue(self):
        result = split_records(records(13))
        self.assertEqual([len(group) for group in result.values()], [60, 6, 12])

    def test_rejects_duplicate_ids_and_content(self):
        for duplicate_content in (False, True):
            rows = records(10)
            if duplicate_content:
                rows[1]["text"] = rows[0]["text"]
            else:
                rows[1]["dialogue_id"] = rows[0]["dialogue_id"]
            with self.subTest(content=duplicate_content), self.assertRaisesRegex(ValueError, "Duplicate"):
                split_records(rows)

    def test_invalid_input_does_not_create_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for rows in ([], records(9), [{"dialogue_id": "bad"}], [None]):
                write_jsonl(root / "source.jsonl", rows)
                with self.assertRaises(ValueError):
                    partition(root / "source.jsonl", root / "out")
                self.assertFalse((root / "out").exists())
            (root / "source.jsonl").write_text("not JSON\n")
            with self.assertRaisesRegex(ValueError, "line 1"):
                partition(root / "source.jsonl", root / "out")
            self.assertFalse((root / "out").exists())

    def test_invalid_turns_and_seed(self):
        rows = records(10)
        rows[0]["text"] = '{"dialogue": [{"speaker": "patient", "utterance": "茶。"}]}'
        with self.assertRaises(ValueError):
            split_records(rows)
        with self.assertRaises(ValueError):
            split_records(records(10), -1)

    def test_manifest_hashes_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.jsonl"
            write_jsonl(source, records(10))
            before = source.read_bytes()
            report = partition(source, root / "out")
            self.assertEqual(report["source_sha256"], hashlib.sha256(before).hexdigest())
            self.assertEqual(source.read_bytes(), before)
            for name, metadata in report["splits"].items():
                path = root / "out" / f"{name}.jsonl"
                self.assertEqual(metadata["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
                self.assertEqual(metadata["dialogues"], len(read_jsonl(path)))
            snapshot = {p.name: p.read_bytes() for p in (root / "out").iterdir()}
            with self.assertRaises(FileExistsError):
                partition(source, root / "out")
            self.assertEqual(snapshot, {p.name: p.read_bytes() for p in (root / "out").iterdir()})

    def test_cli(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_jsonl(root / "source.jsonl", records(10))
            result = subprocess.run([sys.executable, "-B", "-m", "gazetalk_zh.split_dialogues",
                                     "--input", str(root / "source.jsonl"), "--output", str(root / "out")],
                                    text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["dialogues"], {"train": 48, "validation": 6, "test": 6})


if __name__ == "__main__":
    unittest.main()
