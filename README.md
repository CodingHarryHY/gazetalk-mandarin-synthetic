# GazeTalk Mandarin synthetic dialogue pipeline

Version: 0.1.4. Status: schema-ordered personas prepared; dialogue generation pending.

This isolated Python package generates fictional therapist-patient conversations
in Simplified Chinese with mainland China usage. Instructions, configuration,
persona descriptions, source code, comments, logs, and documentation are English.
Chinese appears only as dialogue content, language-processing literals,
explicit prompt examples, or test fixtures. This is a research prototype, not a clinical simulator
validated against a Mandarin population.

## Scope and evidence

- Six simulation profiles: anomic, conduction, tcmotor, broca, wernicke, global.
- Three simulation severity bands: mild, moderate, severe. No test-score thresholds.
- Independent complete conversations, generated in one Responses API request.
- Structural validation supports 10-40 speaker turns with alternating roles.
  The six-rule generation prompt requests an even length, a therapist opening,
  and a patient closing turn; these additional prompt requirements need review.
- Five support strategies and 15 topics, listed in [design.md](docs/design.md).
- Fictional personas from authored rules and a fixed seed, without an LLM.
- No restricted transcripts, patient examples, or participant records are ingested.
- No reference-derived rates are claimed. No expert validation has been completed.
- No model training, tablet deployment, or permission to publish/train is implied.

The English implementation's planning, caching, retry, and JSONL patterns informed
this package. It does not import the English package or the v2 control pipeline.
See [sources](docs/sources.md) and [decision history](docs/decisions/README.md).
The [profile evidence register](docs/profile-evidence.md) maps each behaviour
field to background sources or an explicit author choice. The [text-only profile
review](docs/profile-review.md) records a non-clinical inspection of the previous
12-dialogue pilot and the rubric for reviewing new output.

## Six-rule generation prompt (2026-11-11)

The active bundled prompts are `src/gazetalk_zh/resources/prompts/system.txt`
and `session.txt`. They specify topic persistence, cued guessing (one candidate
per turn, at most three guesses per item), no known-answer test questions,
carry-on when meaning is understood, patient-led topic transitions, and
reflection at personally significant moments. They also prevent the therapist
from using persona facts before the patient introduces them.

This project keeps its agreed response format: one question about one point,
no separate declarative sentence before it, and an optional brief supportive
phrase afterwards. This intentionally differs from the prototype's
comment-first variants. Complete submitted patient messages are simulated;
real-time silent waiting actions are outside this dataset's scope. The patient
closes each generated dialogue so the therapist's question is not left dangling.

`configs/pilot_six_rules.toml` preserves the current pilot settings (60 personas,
50 dialogues each, 3000 dialogues total) with a new run directory,
`runs/pilot_six_rules_v1`. It reads the API key from `OPENAI_API_KEY`.
Existing `pilot.toml`, runs, snapshots, and data partitions are not overwritten.

From the repository root, after setting `OPENAI_API_KEY` locally:

```bash
# Offline: prepare personas, planned jobs, and the immutable prompt snapshot.
PYTHONPATH=src .venv/bin/python -B -m gazetalk_zh.cli plan --config configs/pilot_six_rules.toml

# Paid API generation; run only after reviewing the prompts and configuration.
PYTHONPATH=src .venv/bin/python -B -m gazetalk_zh.cli generate --config configs/pilot_six_rules.toml

# Resume an interrupted run with exactly the same configuration and resources.
PYTHONPATH=src .venv/bin/python -B -m gazetalk_zh.cli generate --config configs/pilot_six_rules.toml --resume

# Structural and descriptive checks after generation.
PYTHONPATH=src .venv/bin/python -B -m gazetalk_zh.cli validate --run runs/pilot_six_rules_v1
PYTHONPATH=src .venv/bin/python -B -m gazetalk_zh.cli evaluate --run runs/pilot_six_rules_v1
```

Once `plan` creates a snapshot, changing the prompts, catalogs, configuration,
or pipeline source requires a new `run_dir`. Do not resume an old run with
these new prompts. Review and edit settings before planning.

These changes update generation instructions, not the output schema or semantic
acceptance checks. `validate`/`evaluate` cannot certify the six conversation
rules, the one-question requirement, or clinical quality. Human review is still
required. Existing datasets and the separate fine-tuning workflow retain their
previous versions until explicitly migrated.

## Environment and commands

Python 3.11 or later is required. From the repository root:

~~~bash
uv run  gazetalk-zh personas --config /configs/batch_2000.toml
uv run  gazetalk-zh plan --config /configs/batch_2000.toml
uv run  gazetalk-zh plan --config /configs/pilot.toml
~~~

The personas and plan commands are offline and idempotent. Both prepare an
immutable run bundle with personas, field provenance, and the job list. The
personas command exposes the dedicated rule-based persona generation workflow;
the Python function build_personas can also be used independently.

Set generation.api_key in the selected TOML file, or supply OPENAI_API_KEY through
the environment of the generation process. A nonempty configured key takes
precedence; an omitted, empty, or whitespace-only value uses the environment.
An environment variable set in one terminal is not automatically inherited by an
already-running IDE or agent. No .env loader is used.

~~~bash
uv run  gazetalk-zh generate --config /configs/pilot.toml --resume
uv run  gazetalk-zh validate --run /runs/pilot_v0_1_4_ordered
uv run  gazetalk-zh evaluate --run /runs/pilot_v0_1_4_ordered
uv run  gazetalk-zh export --run /runs/pilot_v0_1_4_ordered
~~~

After reviewing the pilot, use batch_2000.toml with generate to run the full
2,000-dialogue design. Planning the full design does not call an API.

The IDE can use mandarin/.venv/bin/python with PYTHONPATH=/src:

~~~bash
PYTHONPATH=/src mandarin/.venv/bin/python -B -m gazetalk_zh plan --config /configs/pilot.toml
PYTHONPATH=/src mandarin/.venv/bin/python -B -m unittest discover -s /tests -v
~~~

All relative asset paths and run_dir in TOML resolve relative to the config file,
not the current directory. Package prompts and schemas are bundled resources;
the editable catalogs and run configs remain explicit files.

## Prompt/completion conversion

Convert each already-split training, validation, or test JSONL file separately,
without changing dataset splits:

~~~bash
uv run python -m gazetalk_zh.dialogue_to_samples --input runs/pilot_v0_1_8/dialogues.jsonl --output runs/pilot_v0_1_8/samples.jsonl
~~~

Each input line must contain a `text` JSON string with a `dialogue` array of
`speaker`/`utterance` objects. Each therapist turn except an opening turn becomes
one sample: `prompt` contains a fixed Chinese system instruction and all preceding
turns; `completion` contains only the target assistant message. Patient turns map
to `user`, therapist turns to `assistant`. Text is preserved without truncation,
and metadata is omitted. Both output fields are message arrays.

The converter reports dialogue/sample counts and stops with an input line number
on invalid records. It does not leave output for invalid input or overwrite an
existing output file. The output parent directory must exist. Configure the
training pipeline to compute loss only on `completion`, excluding all prompt
tokens, including previous assistant replies.

## Configuration

Set the API base URL in the existing [generation] section of the chosen TOML:

~~~toml
[generation]
backend = "openai"
base_url = "https://gateway.example/v1"
api_key = ""
model = "gpt-6-luna"
~~~

This is a partial example: keep the other generation settings already in the file.
Replace the example host with your provider's actual base URL. If omitted,
base_url defaults to https://api.openai.com/v1. A trailing slash is normalized.
Use the provider's base path (often /v1), not /responses or /chat/completions.
HTTP is supported for local endpoints; HTTPS is also supported. URLs with embedded
credentials, query strings, fragments, or whitespace are rejected. Fill api_key
with the credential accepted by your endpoint, or leave it blank for OPENAI_API_KEY.
OPENAI_BASE_URL is not read: the TOML/default address is passed explicitly to the SDK.

The config key is extracted into a runtime-only field, excluded from Config repr,
snapshots, fingerprints, prompts, and request-body logs. Configuration errors do
not echo input values. Changing only the key does not invalidate resume within
the same pipeline version. The plaintext key remains in the original TOML file;
this mechanism does not encrypt or remove it from that file.

The selected service receives the fictional prompt and supplied API key. It must
support the Responses API, strict JSON Schema, and the configured model/request
options. Changing the base URL does not add Chat Completions or Azure-specific
authentication support. No custom endpoint has been tested live.

The effective URL is recorded in the run snapshot and included in its fingerprint.
After changing it, choose a fresh run_dir before preparing personas. Version 0.1.4
defaults use pilot_v0_1_4_ordered and batch_2000_v0_1_4; earlier run bundles are preserved.
Re-running persona preparation with the same rules and seed retains the same
persona attributes. Changing only the endpoint does not change the persona design.

| Setting | Pilot | Full design |
|---|---:|---:|
| persona_count | 12 | 50 |
| dialogues_per_persona | 3 | 40 |
| total dialogues | 36 | 2,000 |
| min_turns / max_turns | 10 / 40 | 10 / 40 |
| seed | 42 | 42 |
| model | gpt-6.1-luna | gpt-6-luna |
| reasoning_effort | low | low |
| max_output_tokens | 8,192 | 8,192 |
| max_attempts per job per invocation | 4 | 4 |

A token-limit failure permits a whole-dialogue retry with at most twice the
initial output budget. It never repairs a truncated JSON string by appending text.
SDK retries are disabled so application-level attempts remain auditable.
A completed response with invalid structure is rejected and its validation
feedback is sent with the next complete request. Successful output is flushed
and fsynced record by record. Exhausted jobs remain absent and can be retried.

Fifty personas cannot be exactly balanced across six profiles. Allocation is
9/9/8/8/8/8, with the two extra slots determined by seed. This yields
360/360/320/320/320/320 dialogues when every persona has 40 sessions.
Use 48 or 54 personas for exact equality. These are design quotas, not prevalence.

## Run bundle and resume

Each run contains:

- manifest.json: dates, status, quotas, runtime versions, hashes, and evidence limits.
- snapshot.json: effective non-secret config, catalogs, prompts, schemas, and package source.
- personas.jsonl and persona_provenance.jsonl: fictional inputs and field methods.
  Persona fields, including nested behaviour fields, follow persona.schema.json order.
- jobs.jsonl: deterministic session design, including mode and turn limits.
- dialogues.jsonl: successful records in the established English outer format.
- attempts.jsonl: request payloads, response text, usage, errors, and validation receipts.
- cache.jsonl: validated responses keyed by the exact request.
- errors.jsonl: exhausted or fatal job failures.
- validation.json and quality_flags.jsonl: structural checks and review flags.
- evaluation/: descriptive metrics and summaries.
- exports/<output-hash>/: CHAT files, turn map, review CSV files, and HTML reader.

The main record retains persona_id, dialogue_id, profile, session_index,
session_topic, therapist_strategy, backend, model, cached, input_tokens,
output_tokens, attempt, latency_local, and text. The text field remains a JSON
string containing the dialogue array. The assigned therapist_strategy is a
prompt condition, not verified evidence that the strategy was used correctly.
Actual returned model and response IDs are retained in attempt responses.

Resume requires the same effective config, catalogs, prompts, schemas, and
package source. Existing records must match the job plan, schemas, and validated
attempt receipts. Input tampering, duplicate IDs, malformed lines, incomplete
tails, and incompatible run changes are rejected rather than silently skipped.
A changed implementation or prompt requires a new run_dir. Do not overwrite
a previous snapshot or remove its manifest to bypass this check.

An interrupted write can leave an incomplete final line. Preserve a copy first;
recovery is deliberately manual in v0.1, because automatic truncation could
discard evidence. Missing committed records can be recovered from validated
cache entries. Interrupted starts without terminal events remain visible.

A process lock prevents concurrent run writers on macOS/Linux. Windows is not
supported in v0.1. Hashes detect accidental drift; they are not signed attestations
and do not provide protection against deliberate coordinated modification.

Cached record token fields are zero for that invocation. Original response usage
is retained in the attempt receipt. Evaluation sums reported usage for uncached
outcomes, including failed responses when usage was available. It does not
pretend to know billing for timeouts or unrecorded outcomes.

## Exports and review

CHAT uses zho, INV, and PAR. Sentence splitting may create multiple CHAT main
tiers for one JSON turn. turn_map.jsonl preserves the original utterance and
the mapping. Unicode/ASCII ellipses are normalized to orthographic punctuation
for this export; no measured pause or clinical error annotation is inferred.
Reserved CHAT characters are escaped and every transformation remains traceable.
The export is unsegmented orthographic text, not a Mandarin MOR-ready corpus.

The internal CHAT checker verifies the emitted subset only. It is not CLAN or
Chatter. external_chat_validation remains not_run until an independent official
tool has actually been run. Do not claim compatibility based only on our checker.

Review CSVs contain English metadata, Chinese dialogue content, and empty rating
fields. Ratings are not automatically filled. Suggested ratings: 1 (poor) to
5 (good) for completion, coherence, support, and profile plausibility; yes/no for
stereotype concern. Record reviewer, date, rationale, and unresolved uncertainty.
These are exploratory review dimensions, not validated clinical scales.
The HTML reader is static and does not save edits.

Exports are addressed by output hash. Re-exporting identical output does not
overwrite manual CSV edits. A different output set receives a new directory.
Leading spreadsheet formula characters are escaped in CSV views; JSON retains
the original text.

## Limitations and permissions

Structural success does not establish topic completion, clinical authenticity,
source privacy guarantees, or utility for training a therapist assistant.
Character counts are not words or clinical MLU. Filler/ellipsis metrics are
textual proxies. The near-duplicate detector uses normalized character 5-gram
Jaccard similarity, not semantic equivalence.

Conduction-like phonological behavior and repetition differences are only weakly
represented in text-only everyday conversation. Single-request generation can
produce therapist foreknowledge. Variable length may cluster at prompt limits.
All of these need inspection and later calibration.

No generated dataset license or publication/training permission is granted by
this package. Synthetic status and access to reference corpora do not establish
those permissions. Runs are ignored by Git. No raw corpus importer is included.

## Version discipline

Before changing behavior, create or update an English decision record with the
reason, evidence, alternatives, consequences, validation, and date. Never rewrite
an accepted historical decision as though it had always been the new decision.
Create a successor decision, update the version archive and changelog, and use a
new run directory for changed generation conditions.
