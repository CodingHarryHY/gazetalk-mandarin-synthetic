from __future__ import annotations

import random
from typing import Any

from .config import Config, MODES


def plan_jobs(config: Config, personas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    jobs = []
    for persona in personas:
        rng = random.Random(f"sessions:{config.values['seed']}:{persona['persona_id']}")
        topics = list(persona["topics"])
        strategies = list(config.assets["strategies"])
        modes = list(MODES)
        rng.shuffle(topics)
        rng.shuffle(strategies)
        rng.shuffle(modes)
        for index in range(config.values["dialogues_per_persona"]):
            cycle, position = divmod(index, len(topics))
            jobs.append({
                "persona_id": persona["persona_id"], "profile": persona["profile"],
                "dialogue_id": f"{persona['persona_id']}_D{index + 1:04d}",
                "session_index": index + 1,
                "session_topic": topics[position],
                "therapist_strategy": strategies[(position + cycle) % len(strategies)],
                "conversation_mode": modes[index % len(modes)],
                "scenario_focus": ["one specific occasion", "a preference and its context",
                                   "a small difficulty and what happened", "a meaningful detail"][cycle % 4],
                "min_turns": config.values["min_turns"], "max_turns": config.values["max_turns"],
            })
    random.Random(config.values["seed"]).shuffle(jobs)
    return jobs
