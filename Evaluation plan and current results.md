# Evaluation plan and current results

## Current measured result: bundled smoke fixture

`python run.py --compare` runs the same gold-labelled puzzle through three modes:

1. **Baseline:** take each clue's top candidate independently.
2. **Crossings:** apply arc consistency, then take the highest-confidence candidate remaining in each domain.
3. **Full agent:** apply arc consistency, MRV/degree variable ordering, confidence-ranked search, bounded pattern-aware re-query on a domain wipeout, and backtracking.

The first-pass candidates are generated once per puzzle and reused for all three arms. Any additional pattern-aware requests made by the full agent are counted incrementally. This makes the solver-mode comparison paired and avoids charging duplicate initial generations.

The bundled fixture intentionally ranks incorrect but plausible answers first for two Across clues. Current observed outputs (`python run.py --compare --json`):

| Mode | Word accuracy | Letter accuracy | Exact solve rate | Shared first-pass calls |
|---|---:|---:|---:|---:|
| Baseline | 66.7% | 88.9% | 0% | 6 |
| Crossings | 100% | 100% | 100% | 6 total, shared |
| Full agent | 100% | 100% | 100% | 6 total, shared |

These measurements cover a single 3×3 puzzle with six answer entries. Backtracking is separately tested on an adversarial synthetic CSP; pattern-aware regeneration is separately tested with a provider fixture that only returns the correct entry when given letters derived from fixed neighbors. Do not infer broad ability from this smoke fixture.

## Real-puzzle pilot data

`benchmarks/ashland-2025.json` describes 16 real 2025 puzzles from Steve Weyer via the Ashland.news / CommuniCrossings archive: two 5×5 minis and fourteen standard themed crosswords. Gold grids and clues are read from Across Lite `.puz` solution/clue sections, with every converted entry and crossing validated by the project's grid parser.

The source archive states **CC BY-NC-SA 4.0**. The manifest contains attribution and direct source URLs but not puzzle text. `scripts/prepare_ashland_benchmark.py` fetches and converts the files to `data/real_benchmark/`, which is ignored by Git; it requires `--noncommercial-use` and writes an attribution notice. Do not add the raw files or converted gold data to a public repository. If adaptations are redistributed, comply with the source's attribution and share-alike terms. The corpus is a single-publisher pilot, not a representative or held-out test set.

Prepare and evaluate it with:

```bash
python -m pip install --user -r requirements-benchmark.txt
python scripts/prepare_ashland_benchmark.py --noncommercial-use
mkdir -p results/live
python run.py --compare --provider api \
  --puzzle data/real_benchmark/gold.json --json \
  > results/live/tokenfactory-comparison.json
```

The comparison makes one initial batch request per puzzle, shares those candidates across baseline/crossings/full-agent, and permits only the full agent to make incremental pattern re-queries. The JSON includes exact puzzle-level scores and candidate-generation model, calls, provider-reported token counts, latency, re-query calls, and sanitized failures. An API error is an attempted failure, not silently dropped; the evaluator continues across puzzles where possible. Cost remains null until the dated model rate card is independently verified.

**Hosted-model and real-corpus results have not been checked in.** The real result command must be run with a real Token Factory or OpenAI-compatible key available to the process. Never label the smoke-fixture numbers as Token Factory results. When reporting a completed run, record the model ID, provider endpoint family, run date, manifest version, prompt/code commit, number of attempted and successful puzzles, exact/word/letter rates, request/token totals, latency distribution, and every failed puzzle. Do not publish API secrets, puzzle text, or the restricted local gold dataset.

## Metric definitions

- **Word accuracy:** exact normalized answer matches / gold entries.
- **Letter accuracy:** correctly predicted answer-letter occurrences / total gold answer-letter occurrences across Across and Down entries. Crossed cells count once per entry occurrence; this is distinct from cell-level grid accuracy.
- **Full-puzzle solve rate:** puzzles for which every gold entry is present and correct and solver crossing validation succeeds / puzzles attempted.
- **Calls and tokens:** provider requests and provider-reported input/output tokens. Candidate generation is shared across solver arms; count the common initial generation once, and report full-agent re-queries separately.
- **Latency:** accumulated provider-call wall time; add end-to-end puzzle latency and p50/p95 in a larger benchmark.
- **Failures:** missing key, transport/HTTP/model/JSON errors and puzzle-level unsolved outcomes. Store only sanitized error codes; never serialize credentials or response bodies.
- **Cost:** provider-reported token usage multiplied by a dated, documented model rate card. Current cost is intentionally unestimated.

## Proposed next evaluation steps

1. **Expand the corpus:** use the 16-puzzle local pilot as a smoke/pipeline check, then obtain a permitted, diverse gold-labelled corpus with multiple constructors, sizes, themes, clue types, and difficulty labels. The current source's noncommercial license may not suit every portfolio/repository use.
2. **Lock splits:** split by source/date/theme rather than clue to prevent near-duplicate leakage. Freeze a held-out set before prompt/model tuning. Publish only puzzle identifiers/hashes and metadata where terms allow.
3. **Scale:** target at least 100 puzzles for a directional estimate and several hundred for meaningful comparison. Report exact dataset size and every exclusion.
4. **Paired arms:** compare baseline, propagation, and search using identical first-pass candidate lists. Separately ablate model regeneration and quantify its incremental calls/tokens. Keep provider, model/version, prompt, temperature, timeout, and retry policy fixed.
5. **Repetitions:** for stochastic hosted models, repeat at least three times per puzzle where budget permits. Aggregate per puzzle and use paired differences.
6. **Report:** word and letter accuracy, exact puzzle rate, unresolved/conflicting rate, backtracks, calls, token/latency distributions, and cost per puzzle; stratify by difficulty and clue type. Include paired bootstrap 95% confidence intervals by puzzle and disclose all API failures/timeouts.
7. **Ablations:** disable crossing propagation, confidence ordering, MRV, and backtracking one at a time. Measure held-out exact-solve changes and latency/cost penalties.
8. **Error review:** classify wrong clue semantics, candidate omission, bad confidence ordering, failed pattern-aware re-query, propagation/search bug, malformed input, and API/transport failure. Preserve an auditable trace for every failure.

## Interview interpretation

The included numeric result supports only this narrow claim: **on a deliberately ambiguous 3×3 smoke fixture, deterministic crossings improve exact answers over independent top-candidate selection; separate adversarial tests exercise backtracking and targeted pattern-aware re-query.** The source tree now provides a reproducible 16-puzzle local-data preparation path and paired shared-candidate evaluator, but it does not contain measured real-corpus or hosted-model results. It does not establish generalization, calibrated confidence, or production cost. The next FDE step is to run the local pilot with a verified model, then secure a broader permitted held-out corpus and quantify improvements, error slices, and API cost.
