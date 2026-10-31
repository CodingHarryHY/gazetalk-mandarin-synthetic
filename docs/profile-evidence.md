# Profile behaviour evidence register

Version 0.1.3, reviewed 2026-10-01. This register maps every `behaviour` field in
`configs/profiles.json` to the strongest available support. It does not claim
clinical validation or calibration to a Mandarin population. The exact English
strings are author-written generation instructions, not quotations or measured
rates. The published Chinese classification is a consensus source; the Deng study
is task-specific evidence for anomic discourse only. Neither supplies a numerical
frequency for these fictional everyday conversations.

Source IDs resolve in [sources.md](sources.md). Codes in the matrix:

- `W`: CHINESE-WANG-2021, Chinese subtype/classification background.
- `N`: NAA-GLOSSARY, public subtype description, not Mandarin-specific.
- `A`: ASHA-APHASIA, general aphasia variability or communication behaviour.
- `O`: CONDUCTION-ODELL-1995, small English-language repetition study.
- `D`: MANDARIN-DENG-2024, anomic task sensitivity; not an everyday-dialogue rate.
- `C`: author choice, cautious wording, or a text-only limitation; no direct
  profile-specific evidence for the exact value.

Each cell covers one profile/field pair. A source code supports the *direction* of
the description only. `C` flags the unverified part even when another code appears.

| `behaviour` field | anomic | conduction | tcmotor | broca | wernicke | global |
|---|---|---|---|---|---|---|
| `grammar` | C | C | W, C | W, N, C | N, C | N, C |
| `sentence_length` | D, C | C | W, N, C | W, N, C | N, C | N, C |
| `word_finding` | N, A, C | N, C | A, C | A, C | A, C | A, C |
| `comprehension` | N, C | W, N, C | W, C | W, N, C | W, N, C | W, N, C |
| `repetition` | W, C | W, N, O, C | W, N, C | W, C | W, C | W, C |
| `initiation` | C | C | N, C | N, C | C | C |
| `self_repair` | A, C | O, C | C | C | C | C |
| `semantic_error` | A, C | C | C | C | N, C | C |
| `phonological_error` | C | O, C | C | C | C | C |

## Interpretation by profile

- **Anomic:** Word search is the main supported contrast. Deng et al. show that
  Mandarin anomic output varies with discourse task, so sentence length is not a
  fixed subtype marker. Circumlocution, cue use, and self-repair remain possible,
  not required events. There is no basis here for a per-turn error quota.
- **Conduction:** Relatively preserved comprehension and disproportionate
  repetition difficulty have subtype support. The Odell study observes repeated
  attempts, but in four English-speaking participants. In an everyday conversation
  without a natural repetition opportunity, this distinction may be unobservable.
  Written Chinese cannot establish a phonological error from speech; fabricated
  character spellings are prohibited as a substitute.
- **Transcortical motor:** Reduced spontaneous output and relatively preserved
  repetition are subtype-level background. A grounded follow-up can elicit more
  detail; the prompt should not require consistently terse answers or a test task.
- **Broca:** Effortful, shorter expression has subtype support. The guidance to
  use Mandarin clauses and not treat ordinary subject omission as impairment is a
  language-specific safeguard, not a measured Broca marker in these sources.
- **Wernicke:** Comprehension or meaning mismatch is the strongest supported
  contrast. An everyday dialogue may show a specific misunderstanding followed
  by clarification. Long or incoherent answers in every turn are not required.
- **Global:** Substantial expressive and receptive difficulty has subtype support.
  Whether a particular fictional exchange plausibly fits the `severe` setting
  cannot be confirmed from this text-only evidence register.

`severities` and their allowed combinations remain coverage choices from
[ADR-0002](decisions/0002.md), not diagnostic thresholds. The register deliberately
does not infer rates from the small, differently elicited Mandarin corpora or
present any of these fields as clinical assessment criteria.
