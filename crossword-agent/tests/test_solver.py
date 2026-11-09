import unittest
import json
from unittest.mock import patch

from src.crossword import Crossword
from src.evaluator import evaluate_compare
from src.llm import Candidate, DemoProvider, CandidateProvider, OpenAICompatibleProvider
from src.solver import solve


class MemoryProvider(CandidateProvider):
    def __init__(self, pool):
        super().__init__()
        self.pool = pool

    def generate(self, clue, length, pattern):
        self.calls += 1
        return [Candidate(word, score) for word, score in self.pool[clue]]


class PatternProvider(CandidateProvider):
    def __init__(self):
        super().__init__()
        self.seen = []

    def generate(self, clue, length, pattern):
        self.calls += 1
        self.seen.append((clue, pattern))
        if clue == "top":
            answer = "AB" if pattern == "AB" else "ZZ"
            return [Candidate(answer, .99)]
        fixed = {"left": "AC", "right": "BD", "bottom": "CD"}[clue]
        return [Candidate(fixed, .95)]


class CrosswordSolverTests(unittest.TestCase):
    def test_standard_numbering_and_entries(self):
        puzzle = Crossword(["...", "...", "..."], {
            "1A": "row one", "4A": "row two", "5A": "row three",
            "1D": "column one", "2D": "column two", "3D": "column three",
        })
        self.assertEqual(set(puzzle.entries), {"1A", "4A", "5A", "1D", "2D", "3D"})
        self.assertEqual(puzzle.entries["4A"].length, 3)
        self.assertEqual(len(puzzle.crossings), 9)

    def test_demo_agent_solves_using_crossings(self):
        from pathlib import Path
        import json
        item = json.loads(Path("data/sample_puzzles.json").read_text())[0]
        puzzle = Crossword.from_dict(item)
        provider = DemoProvider()
        result = solve(puzzle, provider, "agent")
        self.assertTrue(result.solved)
        self.assertEqual(result.answers, item["answers"])
        self.assertTrue(any(event["type"] == "prune" for event in result.events))
        self.assertEqual(provider.calls, 6)

    def test_agent_backtracks_after_a_confident_but_bad_branch(self):
        puzzle = Crossword(["..", ".."], {
            "1A": "top", "1D": "left", "2D": "right", "3A": "bottom",
        })
        abc = [("AA", .8), ("BB", .8), ("CC", .8)]
        # Three edges enforce equality of the hidden symbol; the right edge
        # rotates it. Arc consistency retains every local option, but the
        # top-ranked BB branch is globally impossible. The lower-ranked AA
        # candidate plus the extra AA right-edge candidate is a valid solution.
        pool = {
            "top": [("BB", .99), ("AA", .6), ("CC", .3)],
            "left": abc,
            "right": [("AB", .9), ("BC", .8), ("CA", .7), ("AA", .6)],
            "bottom": abc,
        }
        result = solve(puzzle, MemoryProvider(pool), "agent")
        self.assertTrue(result.solved)
        self.assertGreaterEqual(result.backtracks, 1)
        self.assertEqual(result.answers["1A"], "AA")
        self.assertTrue(any(event["type"] == "backtrack" for event in result.events))

    def test_agent_requeries_empty_domain_with_crossing_pattern(self):
        puzzle = Crossword(["..", ".."], {
            "1A": "top", "1D": "left", "2D": "right", "3A": "bottom",
        })
        provider = PatternProvider()
        result = solve(puzzle, provider, "agent")
        self.assertTrue(result.solved)
        self.assertEqual(result.answers, {"1A": "AB", "1D": "AC", "2D": "BD", "3A": "CD"})
        self.assertIn(("top", "AB"), provider.seen)
        self.assertTrue(any(event["type"] == "regenerate" and event["pattern"] == "AB" for event in result.events))

    def test_api_provider_batches_and_filters_candidates(self):
        class FakeResponse:
            def __enter__(self):
                return self
            def __exit__(self, *_args):
                return False
            def read(self):
                content = json.dumps({"entries": {
                    "1A": [{"answer": "CAT", "confidence": .9}, {"answer": "CAR", "confidence": .8}],
                    "1D": [{"answer": "ARE", "confidence": .7}, {"answer": "CAT", "confidence": .6}],
                }})
                return json.dumps({"choices": [{"message": {"content": content}}], "usage": {"prompt_tokens": 20, "completion_tokens": 12}}).encode()

        provider = OpenAICompatibleProvider(api_key="test-key", base_url="https://example.test/v1", model="test-model")
        with patch("src.llm.urllib.request.urlopen", return_value=FakeResponse()) as mocked:
            got = provider.generate_many({"1A": ("feline", 3, "C_T"), "1D": ("exist", 3, "A__")})
        self.assertEqual(mocked.call_count, 1)
        self.assertEqual([c.answer for c in got["1A"]], ["CAT"])
        self.assertEqual([c.answer for c in got["1D"]], ["ARE"])
        self.assertEqual(provider.calls, 1)
        self.assertEqual(provider.input_tokens, 20)
        self.assertEqual(provider.output_tokens, 12)

    def test_token_factory_never_falls_back_to_openai_secret(self):
        import os
        with patch.dict(os.environ, {
            "TOKEN_FACTORY_BASE_URL": "https://api.tokenfactory.nebius.com/v1",
            "TOKEN_FACTORY_API_KEY": "",
            "OPENAI_API_KEY": "openai-secret-must-not-be-used",
        }, clear=True):
            with self.assertRaisesRegex(ValueError, "TOKEN_FACTORY_API_KEY"):
                OpenAICompatibleProvider()

    def test_compare_shares_first_pass_and_preserves_fixture_results(self):
        report = evaluate_compare("data/sample_puzzles.json", DemoProvider)
        self.assertEqual([row["strategy"] for row in report["strategies"]], ["baseline", "constraints", "agent"])
        self.assertAlmostEqual(report["strategies"][0]["word_accuracy"], 2 / 3)
        self.assertEqual(report["strategies"][1]["full_puzzle_solve_rate"], 1.0)
        self.assertEqual(report["strategies"][2]["full_puzzle_solve_rate"], 1.0)
        self.assertEqual(report["candidate_generation"]["calls"], 6)


if __name__ == "__main__":
    unittest.main()
