from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import random
from typing import Any
import unicodedata

from .provenance import digest, now, write_json, write_jsonl


SPLITS = ("train", "validation", "test")


def split_records(rows: list[dict[str, Any]], seed: int = 42) -> dict[str, list[dict[str, Any]]]:
    """Split whole dialogues within profiles, independent of source record order."""
    if not isinstance(seed, int) or isinstance(seed, bool) or seed < 0:
        raise ValueError("Seed must be a nonnegative integer.")
    if not rows:
        raise ValueError("Input contains no dialogues.")
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    identifiers: set[str] = set()
    contents: set[str] = set()
    for number, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            raise ValueError(f"Record {number}: expected an object.")
        for key in ("dialogue_id", "persona_id", "profile", "text"):
            if not isinstance(row.get(key), str) or not row[key].strip():
                raise ValueError(f"Record {number}: missing or invalid {key}.")
        if row["dialogue_id"] in identifiers:
            raise ValueError(f"Duplicate dialogue_id: {row['dialogue_id']}")
        identifiers.add(row["dialogue_id"])
        try:
            payload = json.loads(row["text"])
        except ValueError as exc:
            raise ValueError(f"Record {number}: invalid dialogue JSON.") from exc
        turns = payload.get("dialogue") if isinstance(payload, dict) else None
        if not isinstance(turns, list) or len(turns) < 2 or len(turns) % 2:
            raise ValueError(f"Record {number}: expected complete therapist/patient turn pairs.")
        normalized = []
        for index, turn in enumerate(turns):
            speaker = "therapist" if index % 2 == 0 else "patient"
            if (not isinstance(turn, dict) or turn.get("speaker") != speaker
                    or not isinstance(turn.get("utterance"), str) or not turn["utterance"].strip()):
                raise ValueError(f"Record {number}: invalid turn {index + 1}.")
            normalized.append((speaker, "".join(unicodedata.normalize("NFKC", turn["utterance"]).split())))
        content_hash = digest(normalized)
        if content_hash in contents:
            raise ValueError("Duplicate normalized complete dialogue; resolve duplicates before splitting.")
        contents.add(content_hash)
        groups[row["profile"]].append(row)

    rng = random.Random(seed)
    result: dict[str, list[dict[str, Any]]] = {name: [] for name in SPLITS}
    for profile in sorted(groups):
        group = sorted(groups[profile], key=lambda row: row["dialogue_id"])
        if len(group) < 10:
            raise ValueError(f"{profile}: need at least 10 dialogues for an 8:1:1 split.")
        rng.shuffle(group)
        train_end = len(group) * 8 // 10
        validation_end = len(group) * 9 // 10
        result["train"].extend(group[:train_end])
        result["validation"].extend(group[train_end:validation_end])
        result["test"].extend(group[validation_end:])
    for group in result.values():
        rng.shuffle(group)
    return result


def partition(input_path: Path, output_dir: Path, seed: int = 42) -> dict[str, Any]:
    if output_dir.exists():
        raise FileExistsError(f"Output directory already exists; use a new directory: {output_dir}")
    source = input_path.read_bytes()
    rows = []
    for number, line in enumerate(source.decode("utf-8").splitlines(), 1):
        try:
            rows.append(json.loads(line))
        except ValueError as exc:
            raise ValueError(f"Invalid JSONL at line {number}.") from exc
    splits = split_records(rows, seed)
    split_ids = {name: {row["dialogue_id"] for row in group} for name, group in splits.items()}
    source_ids = {row["dialogue_id"] for row in rows}
    if (set.union(*split_ids.values()) != source_ids
            or sum(len(ids) for ids in split_ids.values()) != len(source_ids)):
        raise ValueError("Split coverage or disjointness check failed.")
    personas = {name: {row["persona_id"] for row in group} for name, group in splits.items()}
    report: dict[str, Any] = {
        "status": "complete", "created_at": now(), "algorithm": "profile_stratified_shuffle_v1",
        "seed": seed, "ratio": [8, 1, 1], "unit": "complete_dialogue",
        "rounding": "Per profile: train ends at floor(0.8*n), validation at floor(0.9*n), test takes remainder",
        "source": str(input_path.resolve()), "source_sha256": hashlib.sha256(source).hexdigest(),
        "source_dialogues": len(rows), "splitter_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "checks": {"unique_dialogue_ids": True, "no_normalized_complete_duplicates": True,
                   "disjoint_dialogue_ids": True, "complete_coverage": True},
        "persona_overlap": {f"{a}/{b}": len(personas[a] & personas[b])
                            for a, b in (("train", "validation"), ("train", "test"), ("validation", "test"))},
        "scope": "New dialogues for potentially shared fictional personas; not unseen-patient generalization",
        "semantic_quality": "Not evaluated by splitting; no quality filtering performed",
        "splits": {},
    }
    # All input checks finish before creating output; an existing directory is never reused.
    output_dir.mkdir(parents=True, exist_ok=False)
    for name, group in splits.items():
        path = output_dir / f"{name}.jsonl"
        write_jsonl(path, group)
        report["splits"][name] = {
            "file": path.name, "dialogues": len(group),
            "profiles": dict(sorted(Counter(row["profile"] for row in group).items())),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    # A complete manifest is only written after all three data files succeed.
    write_json(output_dir / "split_manifest.json", report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Split complete dialogues by profile into train/validation/test (8:1:1).")
    parser.add_argument("--input", type=Path, required=True, help="Source dialogues.jsonl")
    parser.add_argument("--output", type=Path, required=True, help="New output directory; existing directories are refused")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)
    try:
        report = partition(args.input, args.output, args.seed)
    except (ValueError, OSError) as exc:
        parser.exit(1, f"Error: {exc}\n")
    print(json.dumps({"directory": str(args.output), "seed": args.seed,
                      "dialogues": {name: report["splits"][name]["dialogues"] for name in SPLITS}}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
