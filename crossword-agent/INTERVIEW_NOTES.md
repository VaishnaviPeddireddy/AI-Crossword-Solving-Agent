# Interview discussion notes

## Thirty-second architecture pitch

I split the solver into a semantic candidate generator and a deterministic constraint engine. A provider proposes ranked answers for the full clue list in one batch per puzzle; Python owns grid geometry, entry numbering, length/pattern checks, crossing propagation, and final validation. The full agent selects a constrained entry, tries candidates in confidence order, propagates, may re-query with crossing-derived letters, and backtracks under bounded budgets.

## Design decisions and trade-offs

A language model helps with clue semantics and wordplay but is not reliable at exact grid geometry or cross-answer consistency. AC-3 is cheap and explainable; MRV reduces branching, crossing degree breaks ties, and confidence orders candidates without being treated as calibrated probability. Backtracking handles globally inconsistent assignments that survive local supports. Batching keeps the hosted API to one first-pass request per puzzle; targeted pattern re-queries are incremental and their calls, tokens, and latency are counted separately.

The trade-off is that batch output may be incomplete or malformed and can have higher tail latency than smaller calls. The provider validates candidate lengths and patterns locally and the evaluator records sanitized failures. A production version should add explicit time/token budgets, retries, candidate provenance, and confidence calibration.

## Evaluation: actual evidence

The checked-in measurements are still only the deliberately ambiguous 3×3 smoke fixture: independent top answers score 66.7% word accuracy, 88.9% letter accuracy, and 0% exact solve; crossing constraints and the full agent score 100% on that one puzzle. The deterministic provider makes six clue calls, shared across comparison modes. Unit tests also cover numbering, crossings, a failed branch/backtrack, pattern-aware regeneration, one-call batch parsing, safe Token Factory credential selection, and a synthetic `.puz` conversion.

The repository now contains a 16-puzzle acquisition/import pipeline for 2025 Steve Weyer / Ashland.news files. Their stated CC BY-NC-SA 4.0 license is non-commercial and the puzzle text is intentionally kept out of Git. This is a single-source pilot, not a diverse held-out set. **No real-corpus or live Token Factory accuracy has been measured or claimed yet.** For this environment, the Token Factory API key is not available to the command runner; the model experiment remains blocked until the secret is entered into the secure integration field. The GitHub repository also remains unpublished because prior account authorization was declined.

## Likely follow-up questions

**Why do crossings and the full agent score the same?** The tiny fixture is solvable by arc consistency alone. The synthetic adversarial case shows the separate value of backtracking. Larger paired data is required to quantify the difference.

**How do you compare solver modes fairly?** Generate the initial candidate batch once, replay the same answers to baseline, crossings, and agent, and charge any agent-only pattern re-queries separately. Keep prompts, model, temperature, and puzzle list fixed.

**Is the 16-puzzle benchmark sufficient?** No. It is a real-data pipeline/pilot from one source, and the source license may not fit portfolio redistribution or commercial use. I would next obtain a license-cleared, more diverse corpus and lock a held-out split before tuning.

**How would you evaluate real quality?** Use permitted gold puzzles split by source/date/theme; report exact, word, and letter accuracy; per-puzzle error slices; call/token/latency distributions; and paired confidence intervals. Repeat stochastic hosted-model runs and disclose all failures.

**Why not ask the model for a whole filled grid?** Entry-level proposals plus deterministic constraints make failures localizable and explainable, while avoiding silent cross-answer inconsistencies.
