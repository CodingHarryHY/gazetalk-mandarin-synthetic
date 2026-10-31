# Mandarin v0.1 design

Accepted design date: 2026-09-29 (Europe/Copenhagen).
Implementation status and execution evidence are recorded separately in versions/0.1.0.md.

## Data flow

English authored catalogs -> seeded fictional personas and field provenance ->
deterministic jobs -> English instructions requesting Chinese utterances ->
one OpenAI Responses request per complete dialogue -> strict schema and independent
validation -> successful JSONL and attempt receipts -> descriptive evaluation ->
CHAT and manual review exports.

Restricted Mandarin JiangLin and Mandarin CAP files remain outside this pipeline.
The user reports authorized possession; the implementation has neither read them
nor computed their feature distributions. All numerical generation controls are
research settings, not empirical Mandarin clinical estimates.

## Topics

| ID | Topic | Scope |
|---|---|---|
| T01 | daily routine | Waking, breakfast, outings, evening routine |
| T02 | family memories | Visits, meals, shared experiences |
| T03 | favorite hobbies | Gardening, reading, music, fishing |
| T04 | health and wellbeing | Rest, sleep, walking, expressing discomfort; no medical advice |
| T05 | previous work experience | An ordinary workday, colleagues, a small task |
| T06 | weekend activities | Plans, outings, staying at home |
| T07 | food and cooking | Preferences, groceries, preparing a dish |
| T08 | travel experiences | Transport, visiting family, a trip |
| T09 | community activities | Neighbors, local events, community services |
| T10 | personal stories | An invented memorable or amusing event |
| T11 | shopping and errands | Shopping, collecting a parcel, ordinary errands |
| T12 | a recent appointment | Getting there, waiting, expressing needs; no treatment plans |
| T13 | weather and seasonal activities | Rain, changing seasons, seasonal activities |
| T14 | home tasks | Cleaning, laundry, organizing possessions |
| T15 | friends and social events | Meeting friends, a call, a gathering |

The runtime catalog order corresponds to these IDs. Each persona receives five
distinct candidate topics. Forty sessions cycle through those topics and all
five strategies, varying cycle offsets and both modes. Diversity is planned,
not guaranteed in the generated wording. No between-session memory or recovery
trajectory is assumed.

## Support strategies

- focused questions
- semantic cueing
- yes-no confirmation
- extra response time
- written keyword support

There is one assigned primary strategy per session. Other listed strategies may
be used when appropriate. Phonological cueing, forced choice, gesture, and pointing
are not designated strategies in this version. Written keyword support is
represented textually; no real visual interface is implied.

## Profiles and severity

| Canonical profile | Focus | Initial allowed severity bands |
|---|---|---|
| anomic | Lexical retrieval, circumlocution, self-repair | mild, moderate |
| conduction | Word-form repairs; repetition difficulty only when relevant | mild, moderate |
| tcmotor | Reduced spontaneous initiation and elaboration | mild, moderate, severe |
| broca | Effortful, simplified Mandarin expression | mild, moderate, severe |
| wernicke | Possible semantic or comprehension mismatch | mild, moderate, severe |
| global | Limited information with substantial partner support | severe |

These allowed bands are authored pilot coverage, not diagnostic exclusion rules.
Within a profile, allowed bands are shuffled and cycled, not sampled from an
estimated severity distribution. The six-person pilot samples only one persona
per profile; it cannot test all severity combinations. Global defaults to severe.
The helper normalize_profile accepts anomia and TCmotor aliases; generated
catalogs and records always use canonical lower-case labels.

No WAB score, aphasia quotient, lesion, real biography, or patient identifier is
assigned. Occupation and age are broad fictional context, not predictors of
intelligence or impairment. Behavior profiles specify tendencies, not event
quotas. Fatigue sensitivity is a fictional contextual field only.

## Conversation completion

A complete conversation has a relevant opening, development around a specific
situation, partner support as needed, and a natural closing. It need not contain
successful retrieval of every word. Fixed turn limits do not represent therapy
duration or a recommended rehabilitation dose. The implementation checks structure
exactly and flags selected surface concerns. It does not certify semantic closure.

## Validation scope

Hard checks: JSON syntax and duplicate fields, required/extra properties, role
enumeration and order, configurable turn limits, nonblank utterances, control
characters, record types, plan membership, metadata consistency, unique IDs,
input integrity, and validated-attempt receipts.

Review flags: absence of Han characters in a turn, final question, possible stage
directions, frequent hesitation markers, repeated patient turns. These flags
are heuristic and do not diagnose errors. Short repeated answers may be legitimate.

Descriptive measures: turn counts, Han character counts per role, textual fillers
and ellipses, exact and normalized duplication, within-persona duplication, and
near-duplicate patient text. Group by profile, severity, topic, and conversation mode.
No English LIX, unsegmented word counts, or fabricated real-synthetic distances.

## Engineering changes from the preliminary layout

Prompts and JSON schemas are inside src/gazetalk_zh/resources so installed packages
can locate and ship them. Explicit catalogs remain in configs. This differs from
the preliminary top-level prompts/schemas sketch without changing the workflow.
CSV is generated by the application using Python's standard csv module; there
is no workbook-authoring dependency. JSONL remains the authoritative source.
