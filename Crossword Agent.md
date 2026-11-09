# Crossword Agent

A small, inspectable crossword-solving agent that treats a language model as a **candidate generator**, not as the authority over the grid. Deterministic Python code owns the puzzle state, validates answer lengths and known letters, propagates crossing constraints, and searches/backtracks when a plausible early answer leads to a global contradiction.

## Run it

Requires Python 3.10+. The solver and unit tests use only the Python standard library.

```bash
python run.py                         # deterministic local demonstration; no key required
python -m unittest discover -s tests -v
python run.py --compare               # three solver arms on the bundled smoke fixture
python run.py --strategy agent --provider demo
```

The bundled 3×3 puzzle is deliberately tiny. Two Across distractors are ranked above their gold answers, so the baseline illustrates why crossings matter. It is a smoke test—not evidence of broad crossword performance.

## Optional hosted model

The API provider uses an OpenAI-compatible `/chat/completions` endpoint. Copy `.env.example` to `.env`, set a real key, base URL, and model from the provider's current catalog, then run:

```bash
python run.py --provider api --strategy agent
```

Supported variables are `TOKEN_FACTORY_API_KEY` (or `OPENAI_API_KEY`), `TOKEN_FACTORY_BASE_URL` (or `OPENAI_API_BASE`), and `TOKEN_FACTORY_MODEL` (or `OPENAI_MODEL`). For Nebius Token Factory, the documented base URL is `https://api.tokenfactory.nebius.com/v1`. The provider submits **one structured candidate-generation request per puzzle**, then uses deterministic local validation and search; bounded pattern-aware re-queries may add calls. The evaluator records model name, calls, provider-reported input/output tokens, latency, and failures. It does not print or store API keys. **Never commit `.env` or paste secrets into source code.** Cost is left unreported unless a dated model-specific rate card is verified.

## Real-puzzle pilot benchmark (16 puzzles)

The repository includes a manifest for 16 2025 Ashland.news / Steve Weyer puzzles: 2 five-by-five minis and 14 standard themed puzzles. The source's own archive states **CC BY-NC-SA 4.0** terms. To keep copyrighted puzzle text out of this code repository, the `.puz` files and converted gold grids are fetched only into an ignored local directory; they are **not** in the source ZIP or Git history.

Only use this corpus for non-commercial evaluation. Attribute Steve Weyer and the archive, follow the [CC BY-NC-SA 4.0 terms](https://creativecommons.org/licenses/by-nc-sa/4.0/), and share alike if redistributing adaptations. The importer requires an explicit flag acknowledging the non-commercial restriction:

```bash
python -m pip install --user -r requirements-benchmark.txt
python scripts/prepare_ashland_benchmark.py --noncommercial-use
```

With provider credentials available locally, run the same three solver modes over the common gold corpus:

```bash
mkdir -p results/live
python run.py --compare --provider api \
  --puzzle data/real_benchmark/gold.json --json \
  > results/live/tokenfactory-comparison.json
```

The first candidate batch for each puzzle is shared across baseline, crossing-constraints, and full-agent arms. This makes the comparison paired and avoids three duplicate model calls. Extra agent pattern re-queries are counted separately and included in the overall calls/tokens/latency. The JSON records per-puzzle word/letter accuracy, exact solve, backtracks, incremental calls, model identity, aggregate token usage, and sanitized failures. `data/real_benchmark/`, `.puz`, and `results/live/` are ignored by Git.

The real-puzzle results are **not checked in**: the reproducible smoke-fixture results below are the only measured results in this source tree. The 16-puzzle collection is a single-publisher pilot, not a statistically representative or held-out benchmark. Do not quote real-corpus or hosted-model accuracy until the command has been run with an actual provider and its complete output reviewed.

## Input format

`data/sample_puzzles.json` is a JSON array. Each item has a rectangular grid (`.` open, `#` block, letters/`?` optional known cells), a clue mapping keyed by conventional entry IDs such as `12A` / `12D`, and (for evaluation only) an `answers` gold mapping. Remove `answers` for solve-only input. The parser derives numbering, entry lengths, cell coordinates, and crossings from the grid. The real-data importer performs the same conversion from Across Lite `.puz` files and validates every gold answer and crossing before writing its local dataset.

## Architecture and agent loop

1. Parse the grid into Across/Down entries with coordinates and crossing pairs.
2. Batch clue, length, and current-pattern prompts into a ranked candidate request. The deterministic fixture provider is for reproducibility; the optional hosted provider supplies semantic proposals.
3. Validate candidate length and known-letter patterns in ordinary Python.
4. Run AC-3-style arc consistency: remove candidates that cannot match any answer at a crossing; enqueue neighboring constraints when a domain changes.
5. In full-agent mode, choose the smallest remaining domain (MRV), break ties by crossing degree, try candidates by confidence, propagate, and backtrack on a domain wipeout. When crossings empty a clue domain but neighboring entries fix letters, re-query that clue with the derived pattern; cache each pattern and cap it at two distinct re-queries per entry.
6. Validate every selected crossing before declaring success; show proposal, prune, decision, and undo events in the CLI trace.

The solver exposes `baseline` (top candidate per clue independently), `constraints` (crossing propagation then top remaining candidate), and `agent` (propagation plus backtracking). The comparison reuses the same first-pass candidate lists across the modes; any additional full-agent regeneration is charged to that arm.

## Evaluation

Run `python run.py --compare` or get machine-readable output with `python run.py --compare --json`. The evaluator reports word accuracy, letter accuracy (answer-letter occurrences across entries), exact full-puzzle solve rate, backtracks, candidate-generation calls/tokens/latency, pattern re-queries, and sanitized API failures. Cost is `null` by design unless a trustworthy, dated rate card is supplied.

**Measured bundled-fixture result:**

| Strategy | Word accuracy | Letter accuracy | Exact solve rate | Candidate-generation calls |
|---|---:|---:|---:|---:|
| Baseline | 66.7% | 88.9% | 0% | 6 |
| Crossing constraints | 100% | 100% | 100% | 6 shared |
| Full agent | 100% | 100% | 100% | 6 shared |

These values are reproduced on the single included 3×3 smoke fixture (3 Across + 3 Down clues), not statistically generalizable. See [EVALUATION.md](EVALUATION.md) for the full protocol, pilot-corpus sourcing, restrictions, and limitations. The full-agent backtracking path has a separate adversarial test verifying that it can undo a high-confidence dead end.

## Trade-offs and limitations

- **LLM semantics, code invariants:** natural-language clue interpretation is fuzzy; letter equality, length, and grid geometry are not. Keeping those deterministic makes contradictions explainable and prevents invalid model output from silently corrupting state.
- **Confidence-driven search:** confidence orders candidates but is not treated as calibrated probability. MRV reduces branching; crossing degree is a tie-breaker. The smoke fixture deliberately demonstrates that a plausible top answer can be wrong.
- **Backtracking vs. regeneration:** the full agent can undo a low-confidence assignment and make a bounded, cached pattern-aware re-query when crossings empty a domain. Regeneration adds model calls and is measured separately. A production extension should add per-candidate provenance, explicit request budgets, timeout/retry policy, and confidence calibration.
- **Grid input:** text/JSON grids and imported `.puz` files are supported; image/PDF clue extraction and puzzle-image OCR are out of scope.
- **Dataset size and license:** the bundled result is a smoke test. The 16-puzzle real-data pilot is restricted to non-commercial use by its source license, uses one publisher, and is not bundled. It is not a substitute for a permitted, diverse held-out corpus.
- **Uncertainty:** the CLI does not force-fill a cell when all candidates fail. Partial-answer output and confidence calibration should be added before production use.

## Repository layout

```text
src/crossword.py             grid parsing, numbering, entries, crossings
src/llm.py                   local fixture and batched OpenAI-compatible providers
src/solver.py                validation, AC-3, MRV, search, backtracking
src/evaluator.py             gold metrics and shared-candidate comparisons
scripts/prepare_ashland_benchmark.py  local-only licensed .puz importer
benchmarks/ashland-2025.json  attributed source manifest (no puzzle contents)
data/                         bundled smoke puzzle; downloaded corpus is ignored
 tests/                       regression and API-mocking tests
demo/                         short narrated demonstration and rebuild script
```

## Demo video

`demo/crossword-agent-demo.mp4` is a 47.92-second narration-led walkthrough of the CLI trace, solution, and measured smoke-fixture comparison. Rebuild with `python demo/build_demo.py` (requires Pillow and FFmpeg; narration is included). It demonstrates the bundled sample, not an unrun hosted-model result.
