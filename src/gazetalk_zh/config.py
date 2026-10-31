from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from jsonschema import Draft202012Validator

from .provenance import digest, load_json


PACKAGE = Path(__file__).resolve().parent
PROFILES = ("anomic", "conduction", "tcmotor", "broca", "wernicke", "global")
ALIASES = {"anomia": "anomic", "transcortical_motor": "tcmotor"}
ASSET_FILES = ("profiles_file", "topics_file", "strategies_file", "persona_rules_file")
MODES = ("everyday conversation", "storytelling")
DEFAULT_BASE_URL = "https://api.openai.com/v1"


def validate_base_url(value: str) -> str:
    message = "generation.base_url must be an HTTP(S) base URL without credentials, query, fragment, or whitespace."
    try:
        parsed = urlsplit(value)
        port = parsed.port
        if (parsed.scheme not in ("http", "https") or not parsed.hostname
                or parsed.username is not None or parsed.password is not None
                or "?" in value or "#" in value or "\\" in value
                or any(char.isspace() or ord(char) < 32 for char in value)
                or port == 0):
            raise ValueError(message)
    except ValueError:
        raise ValueError(message) from None
    if parsed.path.rstrip("/").endswith(("/responses", "/chat/completions")):
        raise ValueError("generation.base_url must be the API base, not a responses or chat/completions endpoint.")
    return value.rstrip("/")


def normalize_profile(value: str) -> str:
    value = value.strip().lower()
    value = ALIASES.get(value, value)
    if value not in PROFILES:
        raise ValueError("Unsupported simulation profile.")
    return value


@dataclass(frozen=True)
class Config:
    values: dict[str, Any]
    assets: dict[str, Any]
    resources: dict[str, str]
    source: dict[str, str]
    run_dir: Path
    api_key: str | None = field(default=None, repr=False, compare=False)

    @property
    def fingerprint(self) -> str:
        return digest({"config": self.values, "assets": self.assets,
                       "resources": self.resources, "source": self.source})


def load_config(path: Path) -> Config:
    try:
        values = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError:
        raise ValueError("Invalid TOML configuration; check quoting and field syntax.") from None
    integer = {"type": "integer", "minimum": 1}
    string = {"type": "string", "minLength": 1}
    properties: dict[str, Any] = {
        "config_version": {"const": "zh-config-v0.1"},
        "seed": {"type": "integer", "minimum": 0},
        "persona_count": {"type": "integer", "minimum": 6},
        "dialogues_per_persona": integer, "min_turns": {"type": "integer", "minimum": 2},
        "max_turns": {"type": "integer", "minimum": 2}, "run_dir": string,
        **{key: string for key in ASSET_FILES},
        "generation": {"type": "object", "additionalProperties": False,
            "required": ["backend", "model", "reasoning_effort", "max_output_tokens",
                         "max_attempts", "timeout_seconds", "retry_wait_seconds", "request_pause_seconds"],
            "properties": {"backend": {"const": "openai"}, "model": string, "base_url": string,
                "api_key": {"type": "string"},
                "reasoning_effort": {"enum": ["none", "low", "medium", "high", "xhigh", "max"]},
                "service_tier": {"const": "fast"},
                "max_output_tokens": integer, "max_attempts": integer,
                "timeout_seconds": integer,
                "retry_wait_seconds": {"type": "number", "minimum": 0},
                "request_pause_seconds": {"type": "number", "minimum": 0}}},
    }
    validator = Draft202012Validator({"type": "object", "additionalProperties": False,
                                     "required": list(properties), "properties": properties})
    errors = list(validator.iter_errors(values))
    if errors:
        raise ValueError("Invalid configuration (schema keyword: " + errors[0].validator + ").")
    api_key = values["generation"].pop("api_key", "").strip() or None
    values["generation"]["base_url"] = validate_base_url(values["generation"].get("base_url", DEFAULT_BASE_URL))
    if values["min_turns"] > values["max_turns"]:
        raise ValueError("min_turns must not exceed max_turns.")
    assets = {key.removesuffix("_file"): load_json(path.parent / values[key]) for key in ASSET_FILES}
    if set(assets["profiles"]) != set(PROFILES):
        raise ValueError("The profile catalog must contain exactly the six approved profiles.")
    for key in ("topics", "strategies"):
        items = assets[key]
        if not isinstance(items, list) or not items or any(not isinstance(v, str) or not v.strip() for v in items):
            raise ValueError(f"Invalid {key} catalog.")
        if len(set(items)) != len(items):
            raise ValueError(f"Duplicate {key} catalog entries.")
    rules = assets["persona_rules"]
    for key in ("age_bands", "occupation_categories", "fatigue_sensitivities"):
        if not rules.get(key) or len(set(rules[key])) != len(rules[key]):
            raise ValueError(f"Invalid or duplicate persona rule: {key}.")
    for rule, catalog in (("topics_per_persona", "topics"), ("supports_per_persona", "strategies")):
        value = rules.get(rule)
        if type(value) is not int or not 1 <= value <= len(assets[catalog]):
            raise ValueError(f"Invalid persona rule: {rule}.")
    for profile in assets["profiles"].values():
        if not profile.get("severities") or not set(profile["severities"]) <= {"mild", "moderate", "severe"}:
            raise ValueError("Invalid profile severity choices.")
    if not json.dumps(assets, ensure_ascii=False).isascii():
        raise ValueError("Auxiliary catalog text must be in English (ASCII in v0.1).")
    resources = {str(p.relative_to(PACKAGE / "resources")): p.read_text(encoding="utf-8")
                 for p in sorted((PACKAGE / "resources").rglob("*")) if p.is_file()}
    source = {p.name: p.read_text(encoding="utf-8") for p in sorted(PACKAGE.glob("*.py"))}
    return Config(values, assets, resources, source, (path.parent / values["run_dir"]).resolve(), api_key=api_key)
