from __future__ import annotations

import json
import re
from pathlib import Path
from statistics import mean

from .crossword import Crossword
from .llm import Candidate, CandidateProvider, DemoProvider
from .solver import SolveResult, solve


STRATEGIES = ("baseline", "constraints", "agent")


def _load_items(dataset_path: str | Path) -> list[dict]:
    data = json.loads(Path(dataset_path).read_text(encoding="utf-8"))
    return data if isinstance(data, list) else [data]


def _score(gold: dict[str, str], result: SolveResult) -> tuple[int, int, int, bool]:
    word_correct = sum(result.answers.get(key, "") == answer for key, answer in gold.items())
    letter_correct = sum(
        i < len(result.answers.get(key, "")) and result.answers[key][i] == char
        for key, answer in gold.items() for i, char in enumerate(answer)
    )
    letter_total = sum(map(len, gold.values()))
    exact = result.solved and all(result.answers.get(key) == answer for key, answer in gold.items())
    return word_correct, letter_correct, letter_total, exact


def _safe_error(exc: Exception) -> str:
    match = re.search(r"HTTP (\d{3})", str(exc))
    if match:
        return f"http_{match.group(1)}"
    if isinstance(exc, ValueError) and "TOKEN_FACTORY_API_KEY" in str(exc):
        return "missing_api_key"
    return type(exc).__name__


def evaluate(dataset_path: str | Path, strategy: str = "agent", provider_factory=DemoProvider) -> dict:
    """Evaluate one solver mode; each API provider batches initial clues per puzzle."""
    data = _load_items(dataset_path)
    word_correct = word_total = letter_correct = letter_total = puzzle_correct = 0
    runs = []
    failures = []
    for item in data:
        puzzle = Crossword.from_dict(item)
        gold = {key: answer.upper() for key, answer in item["answers"].items()}
        try:
            provider: CandidateProvider = provider_factory()
            result = solve(puzzle, provider, strategy)
            w_ok, l_ok, l_total, exact = _score(gold, result)
            error = None
        except Exception as exc:
            provider = None
            result = SolveResult({}, False)
            w_ok, l_ok, l_total, exact = 0, 0, sum(map(len, gold.values())), False
            error = _safe_error(exc)
            failures.append({"puzzle_id": item.get("id", "unnamed"), "error": error})
        word_correct += w_ok
        word_total += len(gold)
        letter_correct += l_ok
        letter_total += l_total
        puzzle_correct += exact
        runs.append({
            "puzzle_id": item.get("id", "unnamed"),
            "word_accuracy": round(w_ok / max(len(gold), 1), 4),
            "letter_accuracy": round(l_ok / max(l_total, 1), 4),
            "exact_solve": exact,
            "api_calls": provider.calls if provider else 0,
            "input_tokens": provider.input_tokens if provider else 0,
            "output_tokens": provider.output_tokens if provider else 0,
            "latency_seconds": round(provider.elapsed_seconds, 4) if provider else 0,
            "backtracks": result.backtracks,
            "error": error,
        })
    return {
        "strategy": strategy,
        "puzzles": len(data),
        "word_accuracy": word_correct / max(word_total, 1),
        "letter_accuracy": letter_correct / max(letter_total, 1),
        "full_puzzle_solve_rate": puzzle_correct / max(len(data), 1),
        "avg_api_calls": mean(run["api_calls"] for run in runs) if runs else 0,
        "avg_input_tokens": mean(run["input_tokens"] for run in runs) if runs else 0,
        "avg_output_tokens": mean(run["output_tokens"] for run in runs) if runs else 0,
        "avg_latency_seconds": mean(run["latency_seconds"] for run in runs) if runs else 0,
        "cost_usd": None,
        "cost_note": "Not estimated until a dated model rate card is verified.",
        "failures": failures,
        "runs": runs,
    }


class _CachedCandidates(CandidateProvider):
    """Replay common first-pass candidates; only the full agent may request a new pattern."""

    name = "shared-candidate-cache"

    def __init__(self, candidates: dict[str, list[Candidate]], request_specs: dict[str, tuple[str, int, str]], live_provider: CandidateProvider | None = None):
        super().__init__()
        self.candidates = candidates
        self.request_specs = request_specs
        self.live_provider = live_provider
        self.by_clue = {(clue, int(length)): (pattern, candidates.get(entry_id, [])) for entry_id, (clue, length, pattern) in request_specs.items()}
        self.errors: list[str] = []

    @staticmethod
    def _filter(values: list[Candidate], length: int, pattern: str) -> list[Candidate]:
        return [c for c in values if len(c.answer) == length and all(p == "_" or p == a for p, a in zip(pattern, c.answer))]

    def generate_many(self, requests: dict[str, tuple[str, int, str]]) -> dict[str, list[Candidate]]:
        return {
            entry_id: self._filter(self.candidates.get(entry_id, []), length, pattern)
            for entry_id, (_clue, length, pattern) in requests.items()
        }

    def generate(self, clue: str, length: int, pattern: str) -> list[Candidate]:
        initial = self.by_clue.get((clue, int(length)))
        if initial and pattern == initial[0]:
            return self._filter(initial[1], length, pattern)
        if self.live_provider is None:
            return self._filter(initial[1], length, pattern) if initial else []
        try:
            return self.live_provider.generate(clue, length, pattern)
        except Exception as exc:
            self.errors.append(_safe_error(exc))
            return []


def evaluate_compare(dataset_path: str | Path, provider_factory=DemoProvider) -> dict:
    """Compare modes on common initial candidate lists; count model generation once.

    The batch-generated first pass is shared across all three solver arms. The
    full agent may add bounded pattern-aware calls; those incremental calls are
    separately included in the total token/call/latency accounting.
    """
    data = _load_items(dataset_path)
    sums = {
        strategy: {"word_correct": 0, "word_total": 0, "letter_correct": 0, "letter_total": 0, "puzzle_correct": 0, "backtracks": [], "decisions": [], "requery_calls": 0, "runs": []}
        for strategy in STRATEGIES
    }
    generation = {"provider": None, "model": None, "puzzles": len(data), "calls": 0, "input_tokens": 0, "output_tokens": 0, "latency_seconds": 0.0, "failures": []}

    for item in data:
        puzzle = Crossword.from_dict(item)
        gold = {key: answer.upper() for key, answer in item["answers"].items()}
        request_specs = {
            entry_id: (entry.clue, entry.length, puzzle.pattern(entry_id))
            for entry_id, entry in puzzle.entries.items()
        }
        try:
            live = provider_factory()
            generation["provider"] = getattr(live, "name", type(live).__name__)
            generation["model"] = getattr(live, "model", generation["model"])
            candidate_lists = live.generate_many(request_specs)
        except Exception as exc:
            live = None
            candidate_lists = {key: [] for key in request_specs}
            generation["failures"].append({"puzzle_id": item.get("id", "unnamed"), "stage": "initial_batch", "error": _safe_error(exc)})

        for strategy in STRATEGIES:
            cached = _CachedCandidates(candidate_lists, request_specs, live if strategy == "agent" else None)
            before = (live.calls, live.input_tokens, live.output_tokens, live.elapsed_seconds) if live else (0, 0, 0, 0.0)
            try:
                result = solve(puzzle, cached, strategy)
                error = None
            except Exception as exc:
                result = SolveResult({}, False)
                error = _safe_error(exc)
                generation["failures"].append({"puzzle_id": item.get("id", "unnamed"), "stage": strategy, "error": error})
            after = (live.calls, live.input_tokens, live.output_tokens, live.elapsed_seconds) if live else before
            added = tuple(after[i] - before[i] for i in range(4))
            if strategy == "agent":
                generation["calls"] += added[0]
                generation["input_tokens"] += added[1]
                generation["output_tokens"] += added[2]
                generation["latency_seconds"] += added[3]
                sums[strategy]["requery_calls"] += added[0]
                for cache_error in cached.errors:
                    generation["failures"].append({"puzzle_id": item.get("id", "unnamed"), "stage": "pattern_requery", "error": cache_error})

            # Initial batch generation is counted exactly once per puzzle and is
            # attached here after baseline; incremental re-queries belong to agent.
            if strategy == "baseline" and live:
                generation["calls"] += live.calls
                generation["input_tokens"] += live.input_tokens
                generation["output_tokens"] += live.output_tokens
                generation["latency_seconds"] += live.elapsed_seconds

            w_ok, l_ok, l_total, exact = _score(gold, result)
            agg = sums[strategy]
            agg["word_correct"] += w_ok
            agg["word_total"] += len(gold)
            agg["letter_correct"] += l_ok
            agg["letter_total"] += l_total
            agg["puzzle_correct"] += exact
            agg["backtracks"].append(result.backtracks)
            agg["decisions"].append(result.decisions)
            agg["runs"].append({
                "puzzle_id": item.get("id", "unnamed"),
                "word_accuracy": round(w_ok / max(len(gold), 1), 4),
                "letter_accuracy": round(l_ok / max(l_total, 1), 4),
                "exact_solve": exact,
                "backtracks": result.backtracks,
                "decisions": result.decisions,
                "incremental_model_calls": added[0] if strategy == "agent" else 0,
                "error": error,
            })

    reports = []
    for strategy in STRATEGIES:
        agg = sums[strategy]
        reports.append({
            "strategy": strategy,
            "puzzles": len(data),
            "word_accuracy": agg["word_correct"] / max(agg["word_total"], 1),
            "letter_accuracy": agg["letter_correct"] / max(agg["letter_total"], 1),
            "full_puzzle_solve_rate": agg["puzzle_correct"] / max(len(data), 1),
            "avg_backtracks": mean(agg["backtracks"]) if agg["backtracks"] else 0,
            "avg_decisions": mean(agg["decisions"]) if agg["decisions"] else 0,
            "agent_pattern_requery_calls": agg["requery_calls"] if strategy == "agent" else 0,
            "runs": agg["runs"],
        })
    generation["latency_seconds"] = round(generation["latency_seconds"], 4)
    generation["cost_usd"] = None
    generation["cost_note"] = "Not estimated until a dated model rate card is verified."
    return {
        "comparison_note": "Each puzzle's initial candidate batch is generated once and reused across all three solver arms; full-agent pattern-aware re-queries are incremental and included in candidate_generation totals.",
        "candidate_generation": generation,
        "strategies": reports,
    }
