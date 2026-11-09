from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass


@dataclass(frozen=True)
class Candidate:
    answer: str
    confidence: float
    rationale: str = ""

    @classmethod
    def from_value(cls, value: dict) -> "Candidate":
        answer = re.sub(r"[^A-Z]", "", str(value.get("answer", "")).upper())
        confidence = float(value.get("confidence", 0.5))
        return cls(answer, min(1.0, max(0.0, confidence)), str(value.get("rationale", "")))


class CandidateProvider:
    name = "base"

    def __init__(self):
        self.calls = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.elapsed_seconds = 0.0

    def generate(self, clue: str, length: int, pattern: str) -> list[Candidate]:
        raise NotImplementedError

    def generate_many(self, requests: dict[str, tuple[str, int, str]]) -> dict[str, list[Candidate]]:
        """Default adapter; providers may override this to batch one whole grid."""
        return {entry_id: self.generate(clue, length, pattern) for entry_id, (clue, length, pattern) in requests.items()}

    def _record(self, start: float) -> None:
        self.calls += 1
        self.elapsed_seconds += time.perf_counter() - start


class DemoProvider(CandidateProvider):
    """Reproducible no-key provider; intentionally includes plausible distractors."""

    name = "local-demo"
    POOL = {
        "Feline pet": [("CAR", .96), ("CAT", .91), ("COT", .25)],
        "Exist": [("AGE", .93), ("ARE", .88), ("ATE", .35)],
        "Number after nine": [("TEN", .98), ("TWO", .35), ("ONE", .25)],
        "Domestic feline": [("CAT", .98), ("CAR", .35), ("COT", .20)],
        "Second-person plural of be": [("ARE", .99), ("ERA", .20), ("ARM", .10)],
        "Cardinal number following nine": [("TEN", .99), ("NET", .20), ("ONE", .10)],
    }

    def generate(self, clue: str, length: int, pattern: str) -> list[Candidate]:
        start = time.perf_counter()
        clue_key = re.sub(r"\s*\(\d+\)\s*$", "", clue).strip()
        candidates = [Candidate(answer, score, "local fixture candidate") for answer, score in self.POOL.get(clue_key, [])]
        candidates = [c for c in candidates if len(c.answer) == length and all(p == "_" or p == a for p, a in zip(pattern, c.answer))]
        self._record(start)
        return candidates


class OpenAICompatibleProvider(CandidateProvider):
    """OpenAI-compatible chat adapter; initial clue candidates are batched per grid."""

    name = "openai-compatible"

    def __init__(self, api_key: str | None = None, base_url: str | None = None, model: str | None = None):
        super().__init__()
        tf_base = os.getenv("TOKEN_FACTORY_BASE_URL")
        openai_base = os.getenv("OPENAI_API_BASE")
        if base_url:
            selected_base = base_url
        elif tf_base:
            selected_base = tf_base
        elif openai_base:
            selected_base = openai_base
        elif os.getenv("TOKEN_FACTORY_API_KEY"):
            selected_base = "https://api.tokenfactory.nebius.com/v1"
        else:
            selected_base = "https://api.openai.com/v1"
        self.base_url = selected_base.rstrip("/")
        is_token_factory = "tokenfactory.nebius.com" in self.base_url.lower()
        if api_key:
            self.api_key = api_key
        elif is_token_factory:
            self.api_key = os.getenv("TOKEN_FACTORY_API_KEY")
        else:
            self.api_key = os.getenv("OPENAI_API_KEY")
        self.model = model or (os.getenv("TOKEN_FACTORY_MODEL") if is_token_factory else os.getenv("OPENAI_MODEL")) or ("meta-llama/Llama-3.3-70B-Instruct" if is_token_factory else "gpt-4o-mini")
        self.name = "nebius-token-factory" if is_token_factory else "openai-compatible"
        if not self.api_key or self.api_key.strip().lower() in {"your_api_key_here", "<api-key>"}:
            raise ValueError("Set a real TOKEN_FACTORY_API_KEY (or OPENAI_API_KEY) to use the API provider")
        self.last_usage: dict[str, int] = {"input_tokens": 0, "output_tokens": 0}

    @staticmethod
    def _matches(candidate: Candidate, length: int, pattern: str) -> bool:
        return len(candidate.answer) == length and all(p == "_" or p == a for p, a in zip(pattern, candidate.answer))

    def _chat(self, prompt: str, max_tokens: int) -> dict:
        body = json.dumps({
            "model": self.model,
            "temperature": 0.2,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": "You are a careful crossword clue solver. Follow answer-length and known-letter constraints exactly. Return only valid JSON."},
                {"role": "user", "content": prompt},
            ],
            "response_format": {"type": "json_object"},
        }).encode()
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions", data=body,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        start = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                payload = json.loads(response.read().decode())
        except urllib.error.HTTPError as exc:
            # Avoid echoing response bodies into reports: they may contain sensitive
            # request/provider information. Keep the useful status code only.
            self._record(start)
            raise RuntimeError(f"Model API returned HTTP {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            self._record(start)
            raise RuntimeError(f"Model API request failed ({type(exc).__name__})") from exc
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            self._record(start)
            raise RuntimeError("Model API returned an invalid JSON response") from exc
        self._record(start)
        usage = payload.get("usage", {})
        self.last_usage = {
            "input_tokens": int(usage.get("prompt_tokens", usage.get("input_tokens", 0))),
            "output_tokens": int(usage.get("completion_tokens", usage.get("output_tokens", 0))),
        }
        self.input_tokens += self.last_usage["input_tokens"]
        self.output_tokens += self.last_usage["output_tokens"]
        try:
            content = payload["choices"][0]["message"]["content"]
            return json.loads(content)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise RuntimeError("Model API returned malformed candidate JSON") from exc

    def _parse_candidate_list(self, values, length: int, pattern: str) -> list[Candidate]:
        if isinstance(values, dict):
            values = values.get("candidates", [])
        if not isinstance(values, list):
            return []
        parsed = [Candidate.from_value(value) for value in values if isinstance(value, dict)]
        return [candidate for candidate in parsed if self._matches(candidate, length, pattern)][:5]

    def generate_many(self, requests: dict[str, tuple[str, int, str]]) -> dict[str, list[Candidate]]:
        """Ask for all Across/Down clue candidates in one bounded call per puzzle."""
        if not requests:
            return {}
        entries = [
            {"id": entry_id, "clue": clue, "length": int(length), "pattern": pattern}
            for entry_id, (clue, length, pattern) in requests.items()
        ]
        prompt = (
            "Solve the crossword entries below independently and propose up to 3 ranked candidate answers per entry. "
            "A candidate must have exactly the supplied length and match every known letter; underscores are unknown. "
            "Return one JSON object exactly shaped like {\"entries\":{\"1A\":[{\"answer\":\"WORD\",\"confidence\":0.9}],\"1D\":[...]}}. "
            "Each answer must contain letters only; confidence must be from 0 to 1. Omit rationale to keep the response concise. "
            "Do not invent IDs or omit an entry key. Entries: " + json.dumps(entries, ensure_ascii=False)
        )
        max_tokens = min(5000, max(512, len(entries) * 56))
        parsed = self._chat(prompt, max_tokens)
        mapping = parsed.get("entries", parsed.get("candidates_by_entry", parsed)) if isinstance(parsed, dict) else {}
        if isinstance(mapping, list):
            mapping = {item.get("id"): item.get("candidates", []) for item in mapping if isinstance(item, dict) and item.get("id")}
        if not isinstance(mapping, dict):
            mapping = {}
        result: dict[str, list[Candidate]] = {}
        for entry_id, (_clue, length, pattern) in requests.items():
            result[entry_id] = self._parse_candidate_list(mapping.get(entry_id, []), length, pattern)
        return result

    def generate(self, clue: str, length: int, pattern: str) -> list[Candidate]:
        return self.generate_many({"ENTRY": (clue, length, pattern)}).get("ENTRY", [])
