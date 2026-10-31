from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any

from jsonschema import Draft202012Validator


class ContractError(ValueError):
    pass


def validate_schema(value: Any, schema: dict[str, Any]) -> None:
    errors = sorted(Draft202012Validator(schema).iter_errors(value), key=lambda e: str(list(e.path)))
    if errors:
        error = errors[0]
        # Do not echo arbitrary input values into logs or retry feedback.
        path = "/".join(map(str, error.path)) or "root"
        raise ContractError(f"Schema violation at {path}: {error.validator}.")


def dialogue_schema(resources: dict[str, str], minimum: int, maximum: int) -> dict[str, Any]:
    schema = deepcopy(json.loads(resources["schemas/dialogue.schema.json"]))
    schema["properties"]["dialogue"].update(minItems=minimum, maxItems=maximum)
    return schema


def validate_dialogue(text: str, schema: dict[str, Any]) -> dict[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result = {}
        for key, value in pairs:
            if key in result:
                raise ContractError("Duplicate JSON object field.")
            result[key] = value
        return result

    try:
        parsed = json.loads(text, object_pairs_hook=reject_duplicates)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ContractError("Response is not a valid JSON object.") from exc
    validate_schema(parsed, schema)
    for index, turn in enumerate(parsed["dialogue"]):
        expected = "therapist" if index % 2 == 0 else "patient"
        if turn["speaker"] != expected:
            raise ContractError(f"Wrong speaker at turn {index + 1}; expected {expected}.")
        if not turn["utterance"].strip():
            raise ContractError(f"Blank utterance at turn {index + 1}.")
        if any(ord(char) < 32 and char not in "\n\t" for char in turn["utterance"]):
            raise ContractError(f"Control character at turn {index + 1}.")
    return parsed


def validate_record(row: dict[str, Any], job: dict[str, Any], settings: dict[str, Any],
                    resources: dict[str, str]) -> dict[str, Any]:
    validate_schema(row, json.loads(resources["schemas/record.schema.json"]))
    for key in ("persona_id", "dialogue_id", "profile", "session_index", "session_topic", "therapist_strategy"):
        if row[key] != job[key]:
            raise ContractError(f"Record does not match its planned {key}.")
    for key in ("model", "backend"):
        if row[key] != settings["generation"][key]:
            raise ContractError(f"Record does not match the configured {key}.")
    return validate_dialogue(row["text"], dialogue_schema(resources, settings["min_turns"], settings["max_turns"]))


def quality_flags(dialogue: list[dict[str, str]]) -> list[str]:
    flags = []
    if any(not re.search(r"[\u3400-\u9fff]", t["utterance"]) for t in dialogue):
        flags.append("turn_without_han_characters")
    if dialogue[-1]["utterance"].rstrip().endswith(("?", "？")):
        flags.append("closing_question_requires_review")
    if any(re.search(r"[\[【].+?[\]】]", t["utterance"]) for t in dialogue):
        flags.append("possible_stage_direction")
    patient = [t["utterance"] for t in dialogue if t["speaker"] == "patient"]
    if patient and sum(bool(re.search(r"[嗯呃]|…|\.{3}", t)) for t in patient) / len(patient) > 0.75:
        flags.append("frequent_hesitation_markers")
    if len(set(patient)) < len(patient):
        flags.append("repeated_patient_turn_requires_context")
    return flags
