import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.prepare_ashland_benchmark import convert_puzzle


class BenchmarkImporterTests(unittest.TestCase):
    def test_converts_across_lite_solution_and_validates_crossings(self):
        numbering = types.SimpleNamespace(
            across=[
                {"num": 1, "clue_index": 0, "cell": 0, "len": 3},
                {"num": 4, "clue_index": 4, "cell": 3, "len": 3},
                {"num": 5, "clue_index": 5, "cell": 6, "len": 3},
            ],
            down=[
                {"num": 1, "clue_index": 1, "cell": 0, "len": 3},
                {"num": 2, "clue_index": 2, "cell": 1, "len": 3},
                {"num": 3, "clue_index": 3, "cell": 2, "len": 3},
            ],
        )
        raw = types.SimpleNamespace(
            width=3,
            height=3,
            solution="CATARETEN",
            clues=["feline", "feline", "exist", "number after nine", "exist", "number after nine"],
            clue_numbering=lambda: numbering,
        )
        fake_puz = types.SimpleNamespace(read=lambda _path: raw)
        manifest = {
            "author": "Test author",
            "archive_url": "https://example.test/archive",
            "license": "test license",
            "license_url": "https://example.test/license",
        }
        spec = {"id": "synthetic-3x3", "title": "Synthetic", "url": "https://example.test/puzzle.puz"}
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "synthetic.puz"
            with patch.dict(sys.modules, {"puz": fake_puz}):
                item = convert_puzzle(spec, target, manifest)
        self.assertEqual(item["grid"], ["...", "...", "..."])
        self.assertEqual(item["answers"], {"1A": "CAT", "4A": "ARE", "5A": "TEN", "1D": "CAT", "2D": "ARE", "3D": "TEN"})
        self.assertEqual(len(item["clues"]), 6)


if __name__ == "__main__":
    unittest.main()
