from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any


SYSTEM_PROMPT = "你是 GazeTalk 的中文沟通练习助手。用简短清楚的语言回应；不确定时先确认。"
ROLES = {"patient": "user", "therapist": "assistant"}


def dialogue_samples(record: Any) -> list[dict[str, Any]]:
    if not isinstance(record, dict) or not isinstance(record.get("text"), str):
        raise ValueError("Record must contain a JSON string in 'text'.")
    payload = json.loads(record["text"])
    dialogue = payload.get("dialogue") if isinstance(payload, dict) else None
    if not isinstance(dialogue, list) or not dialogue:
        raise ValueError("'dialogue' must be a nonempty array.")

    history = [{"role": "system", "content": SYSTEM_PROMPT}]
    samples = []
    for index, turn in enumerate(dialogue, 1):
        if not isinstance(turn, dict):
            raise ValueError(f"Turn {index}: expected an object.")
        speaker, utterance = turn.get("speaker"), turn.get("utterance")
        if not isinstance(speaker, str) or speaker not in ROLES:
            raise ValueError(f"Turn {index}: unknown speaker.")
        if not isinstance(utterance, str) or not utterance.strip():
            raise ValueError(f"Turn {index}: utterance must be a nonempty string.")
        message = {"role": ROLES[speaker], "content": utterance}
        if speaker == "therapist" and index > 1:
            samples.append({"prompt": list(history), "completion": [message]})
        history.append(message)
    return samples


def convert(input_path: Path, output_path: Path) -> tuple[int, int]:
    if input_path.resolve() == output_path.resolve():
        raise ValueError("Input and output paths must differ.")
    if output_path.exists():
        raise FileExistsError(f"Output already exists: {output_path}")

    dialogue_count = sample_count = 0
    # Validate into temporary storage so bad input cannot leave a partial dataset.
    with input_path.open(encoding="utf-8") as source, tempfile.TemporaryFile(mode="w+", encoding="utf-8") as staging:
        for line_number, line in enumerate(source, 1):
            try:
                samples = dialogue_samples(json.loads(line))
            except ValueError as exc:
                raise ValueError(f"Input line {line_number}: {exc}") from exc
            for sample in samples:
                staging.write(json.dumps(sample, ensure_ascii=False) + "\n")
            dialogue_count += 1
            sample_count += len(samples)
        staging.seek(0)
        with output_path.open("x", encoding="utf-8") as target:
            for line in staging:
                target.write(line)
    return dialogue_count, sample_count


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Expand dialogues into prompt/completion JSONL samples.")
    parser.add_argument("--input", type=Path, required=True, help="Source dialogues.jsonl")
    parser.add_argument("--output", type=Path, required=True, help="New output JSONL file (parent directory must exist)")
    args = parser.parse_args(argv)
    try:
        dialogues, samples = convert(args.input, args.output)
    except (ValueError, OSError) as exc:
        parser.exit(1, f"Error: {exc}\n")
    print(f"Read {dialogues} dialogues; wrote {samples} samples to {args.output}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
