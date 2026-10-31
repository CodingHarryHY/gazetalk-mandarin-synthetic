from __future__ import annotations

import json
from typing import Any


def build_prompt(persona: dict[str, Any], job: dict[str, Any], assets: dict[str, Any],
                 resources: dict[str, str]) -> tuple[str, str]:
    session = {**job, "allowed_support_strategies": assets["strategies"],
               "language": "Simplified Chinese; mainland China usage",
               "severity_note": "A simulation band, not a measured clinical score",
               "fatigue_note": "A fictional sensitivity, not elapsed time or a measured score"}
    template = resources["prompts/session.txt"]
    user = template.format(persona=json.dumps(persona, ensure_ascii=False, indent=2),
                           session=json.dumps(session, ensure_ascii=False, indent=2))
    return resources["prompts/system.txt"], user
