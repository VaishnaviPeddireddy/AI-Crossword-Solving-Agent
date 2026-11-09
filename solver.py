from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from .crossword import Crossword
from .llm import Candidate, CandidateProvider


@dataclass
class SolveResult:
    answers: dict[str, str]
    solved: bool
    events: list[dict] = field(default_factory=list)
    candidates: dict[str, list[Candidate]] = field(default_factory=dict)
    backtracks: int = 0
    decisions: int = 0


def _compatible(a: str, ia: int, b: str, ib: int) -> bool:
    return a[ia] == b[ib]


def _propagate(crossword: Crossword, domains: dict[str, list[Candidate]], events: list[dict]) -> bool:
    """AC-3 over letter-equality constraints. Returns False on a domain wipeout."""
    queue = deque((a, ia, b, ib) for a, ia, b, ib in crossword.crossings)
    queue.extend((b, ib, a, ia) for a, ia, b, ib in crossword.crossings)
    while queue:
        a, ia, b, ib = queue.popleft()
        supported = [candidate for candidate in domains[a] if any(_compatible(candidate.answer, ia, other.answer, ib) for other in domains[b])]
        removed = [candidate for candidate in domains[a] if candidate not in supported]
        if removed:
            domains[a] = supported
            for candidate in removed:
                events.append({"type": "prune", "entry": a, "answer": candidate.answer, "crossing": b, "reason": "letter mismatch at intersection"})
            if not domains[a]:
                return False
            for x, ix, y, iy in crossword.crossings:
                if y == a and x != b:
                    queue.append((x, ix, a, iy))
                elif x == a and y != b:
                    queue.append((y, iy, a, ix))
    return True


def _pattern_from_singletons(crossword: Crossword, domains: dict[str, list[Candidate]], target: str) -> str | None:
    """Build target's known letters from fixed neighboring entries; None means conflict."""
    letters: dict[tuple[int, int], str] = {}
    for r, row in enumerate(crossword.rows):
        for c, ch in enumerate(row):
            if ch != "." and ch != "#":
                letters[(r, c)] = ch
    for entry_id, values in domains.items():
        if entry_id == target or len(values) != 1:
            continue
        entry = crossword.entries[entry_id]
        for index, cell in enumerate(entry.cells):
            letter = values[0].answer[index]
            if cell in letters and letters[cell] != letter:
                return None
            letters[cell] = letter
    return "".join(letters.get(cell, "_") for cell in crossword.entries[target].cells)


def _search(
    crossword: Crossword,
    domains: dict[str, list[Candidate]],
    events: list[dict],
    counters: dict[str, int],
    provider: CandidateProvider,
    candidate_map: dict[str, list[Candidate]],
    regeneration_cache: dict[tuple[str, str], list[Candidate]],
    attempts: dict[str, int],
) -> dict[str, list[Candidate]] | None:
    if not _propagate(crossword, domains, events):
        # A narrowed pattern may let the semantic provider recover candidates it
        # omitted initially. Bound this to two distinct pattern calls per entry.
        for target in sorted(key for key, values in domains.items() if not values):
            pattern = _pattern_from_singletons(crossword, domains, target)
            if pattern is None or "_" * len(pattern) == pattern:
                continue
            cache_key = (target, pattern)
            if cache_key not in regeneration_cache:
                if attempts.get(target, 0) >= 2:
                    continue
                attempts[target] = attempts.get(target, 0) + 1
                entry = crossword.entries[target]
                generated = provider.generate(entry.clue, entry.length, pattern)
                generated = [c for c in generated if len(c.answer) == entry.length and all(p == "_" or p == a for p, a in zip(pattern, c.answer))]
                regeneration_cache[cache_key] = sorted(generated, key=lambda c: (-c.confidence, c.answer))
                events.append({"type": "regenerate", "entry": target, "pattern": pattern, "answers": [(c.answer, c.confidence) for c in regeneration_cache[cache_key]]})
                for candidate in regeneration_cache[cache_key]:
                    if candidate not in candidate_map[target]:
                        candidate_map[target].append(candidate)
            regenerated = regeneration_cache[cache_key]
            if regenerated:
                retry = {key: list(values) for key, values in domains.items()}
                retry[target] = list(regenerated)
                result = _search(crossword, retry, events, counters, provider, candidate_map, regeneration_cache, attempts)
                if result is not None:
                    return result
        return None
    undecided = [key for key, values in domains.items() if len(values) > 1]
    if not undecided:
        return domains
    degree = {key: sum(1 for a, _, b, _ in crossword.crossings if a == key or b == key) for key in undecided}
    variable = min(undecided, key=lambda key: (len(domains[key]), -degree[key], key))
    choices = sorted(domains[variable], key=lambda item: (-item.confidence, item.answer))
    for candidate in choices:
        counters["decisions"] += 1
        events.append({"type": "try", "entry": variable, "answer": candidate.answer, "confidence": candidate.confidence})
        branch = {key: list(values) for key, values in domains.items()}
        branch[variable] = [candidate]
        result = _search(crossword, branch, events, counters, provider, candidate_map, regeneration_cache, attempts)
        if result is not None:
            return result
        counters["backtracks"] += 1
        events.append({"type": "backtrack", "entry": variable, "answer": candidate.answer})
    return None


def solve(crossword: Crossword, provider: CandidateProvider, strategy: str = "agent") -> SolveResult:
    if strategy not in {"baseline", "constraints", "agent"}:
        raise ValueError("strategy must be baseline, constraints, or agent")
    events: list[dict] = []
    candidate_map: dict[str, list[Candidate]] = {}
    domains: dict[str, list[Candidate]] = {}
    requests = {
        entry_id: (entry.clue, entry.length, crossword.pattern(entry_id))
        for entry_id, entry in crossword.entries.items()
    }
    initial_candidates = provider.generate_many(requests)
    for entry_id, entry in crossword.entries.items():
        pattern = crossword.pattern(entry_id)
        candidates = initial_candidates.get(entry_id, [])
        candidates = [c for c in candidates if len(c.answer) == entry.length and all(p == "_" or p == a for p, a in zip(pattern, c.answer))]
        candidate_map[entry_id] = candidates
        domains[entry_id] = sorted(candidates, key=lambda c: (-c.confidence, c.answer))
        events.append({"type": "candidates", "entry": entry_id, "pattern": pattern, "answers": [(c.answer, c.confidence) for c in domains[entry_id]]})
        if not domains[entry_id]:
            events.append({"type": "empty_domain", "entry": entry_id})
    if any(not values for values in domains.values()):
        return SolveResult({}, False, events, candidate_map)

    counters = {"backtracks": 0, "decisions": 0}
    if strategy == "baseline":
        chosen = {key: values[0] for key, values in domains.items()}
    elif strategy == "constraints":
        if not _propagate(crossword, domains, events):
            return SolveResult({}, False, events, candidate_map)
        chosen = {key: values[0] for key, values in domains.items()}
    else:
        answer_domains = _search(crossword, domains, events, counters, provider, candidate_map, {}, {})
        if answer_domains is None:
            return SolveResult({}, False, events, candidate_map, counters["backtracks"], counters["decisions"])
        chosen = {key: values[0] for key, values in answer_domains.items()}
    answers = {key: candidate.answer for key, candidate in chosen.items()}
    consistent = all(answers[a][ia] == answers[b][ib] for a, ia, b, ib in crossword.crossings if a in answers and b in answers)
    if not consistent:
        events.append({"type": "validation_failed", "reason": "selected answers disagree at a crossing"})
    else:
        events.append({"type": "validated", "entries": len(answers)})
    return SolveResult(answers, consistent and len(answers) == len(crossword.entries), events, candidate_map, counters["backtracks"], counters["decisions"])
