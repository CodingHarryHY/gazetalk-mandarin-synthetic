from __future__ import annotations

import json
import random
from copy import deepcopy
from typing import Any

from .config import Config, PROFILES
from .provenance import digest
from .validation import validate_schema


def balanced_counts(total: int, seed: int) -> dict[str, int]:
    if total < len(PROFILES):
        raise ValueError("At least one persona per profile is required.")
    base, remainder = divmod(total, len(PROFILES))
    order = list(PROFILES)
    random.Random(f"quota:{seed}").shuffle(order)
    return {profile: base + (profile in order[:remainder]) for profile in PROFILES}


def build_personas(config: Config) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    settings, assets = config.values, config.assets
    rules = assets["persona_rules"]
    schema = json.loads(config.resources["schemas/persona.schema.json"])
    personas, provenance = [], []
    counts = balanced_counts(settings["persona_count"], settings["seed"])
    for profile, count in counts.items():
        definition = assets["profiles"][profile]
        severities = list(definition["severities"])
        random.Random(f"severity:{settings['seed']}:{profile}").shuffle(severities)
        for index in range(count):
            identifier = f"ZH_{profile.upper()}_{index + 1:04d}"
            rng = random.Random(f"persona:{settings['seed']}:{identifier}")
            persona = {
                "persona_id": identifier, "profile": profile,
                "age_band": rng.choice(rules["age_bands"]),
                "occupation_category": rng.choice(rules["occupation_categories"]),
                "severity": severities[index % len(severities)],
                "communication_goal": definition["goal"],
                "preferred_support": rng.sample(assets["strategies"], rules["supports_per_persona"]),
                "behaviour_profile": deepcopy(definition["behaviour"]),
                "topics": rng.sample(assets["topics"], rules["topics_per_persona"]),
                "fatigue_sensitivity": rng.choice(rules["fatigue_sensitivities"]),
            }
            validate_schema(persona, schema)
            personas.append(persona)
            methods = {key: "seeded_sampling_from_authored_catalog" for key in persona}
            methods.update(persona_id="synthetic_identifier", profile="near_balanced_research_allocation",
                           severity="seeded_cycle_over_authored_allowed_bands",
                           communication_goal="authored_profile_template",
                           behaviour_profile="authored_profile_tendencies")
            provenance.append({"persona_id": identifier, "persona_hash": digest(persona),
                               "rules_version": rules["version"], "seed": settings["seed"],
                               "reference_status": "not_calibrated", "review_status": "not_reviewed",
                               "source_ids": rules["source_ids"], "field_methods": methods})
    signatures = [digest({k: v for k, v in p.items() if k != "persona_id"}) for p in personas]
    if len(signatures) != len(set(signatures)):
        raise ValueError("Duplicate persona attributes; change the seed or broaden the catalogs.")
    return personas, provenance
