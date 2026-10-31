from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .clients import GenerationError
from .config import load_config
from .evaluate import audit, evaluate
from .exports import export
from .generate import generate, prepare


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate and audit fictional Mandarin dialogues.")
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("personas", "plan", "generate"):
        sub = commands.add_parser(command)
        sub.add_argument("--config", type=Path, required=True)
        if command == "generate":
            sub.add_argument("--resume", action="store_true")
    for command in ("validate", "evaluate", "export"):
        commands.add_parser(command).add_argument("--run", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command in ("personas", "plan", "generate"):
            config = load_config(args.config.resolve())
            result = generate(config, resume=args.resume) if args.command == "generate" else prepare(config)
        elif args.command == "validate":
            result = audit(args.run.resolve())
        elif args.command == "evaluate":
            result = evaluate(args.run.resolve())
        else:
            result = export(args.run.resolve())
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if args.command == "generate" and result["status"] != "complete":
            return 1
        if args.command == "validate" and (result["structural_status"] != "pass" or not result["complete"]):
            return 1
        return 0
    except (ValueError, OSError, GenerationError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
