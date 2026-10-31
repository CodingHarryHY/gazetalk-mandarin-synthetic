# Text-only profile review

Reviewed 2026-10-01 by one assistant, separately from the generation step. This
is a non-clinical text inspection, not an independent human-reader study or
inter-rater assessment, of the 12 already generated
dialogues in `runs/pilot_v0_1_2`. They were produced with the **0.1.2** profile
catalog, before the 0.1.3 edits. There is one fictional persona and two sessions
per profile. No restricted corpus or patient record was used. This review does
not validate the revised profile catalog, clinical realism, or subtype diagnosis.

## Reusable review method

For each dialogue, a Mandarin reader checks: (1) whether a profile's *observable*
distinction appears naturally, (2) whether the partner's response follows what
the patient actually said, (3) whether the Chinese reads naturally and avoids
stereotyped or fabricated sound errors, and (4) whether the speaker retains
agency and the conversation closes coherently. Record `observed`, `unclear`, or
`not elicited` for each opportunity. A missing repetition deficit is `not
elicited` when no natural repetition request occurs, not a profile failure.

Use two independent human readers for a future sample when possible. Resolve
disagreements with the transcript and written criteria, retain both original
judgments, and report agreement before adjudication. Ordinary Mandarin readers
can review surface language and coherence; they cannot certify a clinical type.
Do not use an LLM rating as independent clinical ground truth.

## Existing pilot observations

| Dialogue | Text-level observation | Review flag |
|---|---|---|
| `ZH_ANOMIC_0001_D0001` | Several word searches are resolved by a partner cue; the patient also corrects a preparation detail. | Profile signal observable; check whether repeated cueing feels formulaic. |
| `ZH_ANOMIC_0001_D0002` | Word search and correction occur during a cooking account. | The patient utterance ending `挺舒服的。」` has an unmatched closing quote. |
| `ZH_CONDUCTION_0001_D0001` | The patient revises a spoken form in `慢慢骑` / `满满……骑`; the partner understands the intended meaning. | Character spelling is an uncertain proxy for a speech-sound error. No repetition task occurs. |
| `ZH_CONDUCTION_0001_D0002` | The patient searches for `抹布` and `盐` while describing cooking. | Similar to general naming difficulty; a conduction-specific contrast is not elicited. |
| `ZH_TCMOTOR_0001_D0001` | Short initial answers expand after concrete follow-up questions. | Intended initiation contrast is visible in text. |
| `ZH_TCMOTOR_0001_D0002` | The patient gives several detailed, multi-clause answers. | The initiation contrast is less clear; detail after support need not be an error. |
| `ZH_BROCA_0001_D0001` | The patient conveys a complete cooking event with mostly short clauses. | Text shows concise expression; effort cannot be measured from writing alone. |
| `ZH_BROCA_0001_D0002` | Short clauses and some word search occur without an English-style grammar imitation. | No clear text-level issue. |
| `ZH_WERNICKE_0001_D0001` | Uncertainty about a flower name is clarified, but the patient otherwise tracks the conversation. | An ordinary naming uncertainty is not evidence of a comprehension mismatch. |
| `ZH_WERNICKE_0001_D0002` | A cooking-order mistake is described coherently and corrected. | A procedural mistake is not evidence of language comprehension difficulty. |
| `ZH_GLOBAL_0001_D0001` | Mostly brief answers convey an activity and a preference with partner support. | Short output is visible; clinical severity is not assessable here. |
| `ZH_GLOBAL_0001_D0002` | Brief answers collectively cover a coherent shopping and cooking sequence. | Review whether the amount of independent detail fits the intended setting; no clinical judgment made. |

Across this small baseline, `wernicke` has no clear text-level misunderstanding,
and the second `conduction` dialogue does not display a subtype-specific contrast.
These observations motivate conditional wording and explicit `not elicited`
ratings; they do not justify adding mandatory errors. The 0.1.3 profile catalog
needs a new generated run and the same review before any output-quality claim.
The first 0.1.3 generation attempt produced no dialogues because the configured
local proxy was unreachable; see the [0.1.3 archive](versions/0.1.3.md).
