# Changelog

## 0.1.4 - 2026-10-02

- Write `personas.jsonl` fields in persona schema order, including the nested
  behaviour fields, while retaining canonical sorting for other JSONL records
  and integrity hashes.
- Preserve prior run bundles and use fresh directories for new output.

## 0.1.3 - 2026-10-01

- Reworded six fictional profile behaviour catalogs as conditional, observable
  guidance without required symptom frequencies or invented sound-error spellings.
- Added a field-by-field evidence register and a non-clinical review of the
  previous 12-dialogue pilot, with a reusable review rubric.
- Added Chinese classification and public subtype sources, ADR-0009, and fresh
  pilot/full-design run directories. No restricted corpus comparison was made.

## 0.1.2 - 2026-09-29

- Added optional generation.api_key in TOML, taking precedence over OPENAI_API_KEY.
- Kept credentials out of config snapshots, fingerprints, repr, and request-body logs.
- Allowed credential rotation without invalidating a same-version run.
- Made configuration errors avoid echoing input values.
- Preserved the user's local pilot proxy address and selected fresh v0.1.2 run directories.
- Verified 34 offline tests, including configured-key precedence and artifact exclusion.

## 0.1.1 - 2026-09-29

- Added optional generation.base_url with the official endpoint as the default.
- Passed the validated effective URL explicitly to the SDK and preserved it in run snapshots.
- Added address validation and tests for custom/default routing and changed-endpoint resume rejection.
- Moved default run directories to fresh v0.1.1 paths while preserving v0.1.0 history.
- Verified 30 offline tests; no live custom endpoint request was made.

## 0.1.0 - 2026-09-29

- Added an isolated Mandarin package and non-conflicting CLI.
- Added deterministic six-profile fictional persona generation and field provenance.
- Added a 12-dialogue pilot and a near-balanced 50-persona/2,000-dialogue design.
- Added configurable 10-40-turn complete-dialogue prompts and independent schemas.
- Added OpenAI Responses integration, auditable retries, validated cache, and strict resume.
- Added Chinese character-based descriptive metrics, duplication checks, and review flags.
- Added orthographic CHAT export with a turn map and manual review CSV/HTML.
- Added English design decisions, source boundaries, version archive, and offline tests.
- Live model generation and official external CHAT validation remain separately tracked gates.
