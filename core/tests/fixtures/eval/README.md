# E-02 controlled evaluation fixtures

> 版本：v1.0 · 2026-11-03 · 状态：已定稿

These are manually designed **synthetic**, **unadjudicated** functional fixtures.
No independent human annotators exist for this delivery. `annotators=[]`,
`adjudicated=false`, and the report's gold-quality status is `NOT_RUN` with null kappa.
The probabilities and token counts are hand-authored synthetic values; no model
cassette, real inference, model accuracy, billing or savings evidence is supplied.

The 60 pairs use only fictional ZZAR. Each split has 30 pairs (15 zh, 15 en),
4 overturn / 7 weaken / 5 support / 14 none and subset counts 5/3/3/3/3
(numeric / title_only / adversarial / long / multi_thesis). Numeric kill conditions
appear only in the numeric subset. Planned and cancelled sales are negative for
kill-met; only completed sales are positive. Long passages exceed 800 characters;
multi-thesis pairs share an event and text but have distinct theses.

Both splits are controlled constructions, not a random draw from real SEC data.
The manifest seed controls only deterministic language assignment within these
fixed splits. Its generation field states this provenance explicitly.
The twelve cassette files contain sixty bound frames, including deliberate
uncertainty, a false reminder and a missed reminder. Their dataset/input hashes,
model ID and question-set version are checked before use. The three baseline
examples are synthetic OpenAI-compatible response structures for MockTransport
unit tests; they are never counted as a completed baseline by the CLI.

Use `--mode fixture` explicitly. The default `--mode real` refuses these files.
`--gate` records the v1 threshold experiment but exits 3 because these fixtures
cannot satisfy formal gold/model/sample-size eligibility, even if the experimental
numbers meet the targets. Default MVP-0 replay has no F1 release threshold.
