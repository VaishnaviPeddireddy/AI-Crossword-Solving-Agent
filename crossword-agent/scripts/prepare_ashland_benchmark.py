#!/usr/bin/env python3
"""Fetch and convert the attributed CC BY-NC-SA crossword benchmark locally.

Puzzle files and converted clue/answer grids are intentionally written only to
an ignored local directory; they are not part of the source distribution.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "benchmarks" / "ashland-2025.json"
DEFAULT_OUTPUT = ROOT / "data" / "real_benchmark"
USER_AGENT = "crossword-agent-evaluation/1.0 (local non-commercial benchmark)"


def download(url: str, target: Path, force: bool = False) -> None:
    if target.exists() and not force:
        return
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = response.read(5_000_001)
    if len(payload) > 5_000_000:
        raise ValueError(f"Unexpectedly large puzzle file: {url}")
    if len(payload) < 60 or b"ACROSS&DOWN" not in payload[:64]:
        raise ValueError(f"Not a valid Across Lite .puz file: {url}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)


def convert_puzzle(spec: dict, puz_path: Path, manifest: dict) -> dict:
    try:
        import puz
    except ImportError as exc:
        raise RuntimeError("The benchmark importer needs puzpy; run: python -m pip install -r requirements-benchmark.txt") from exc

    raw = puz.read(str(puz_path))
    width, height = int(raw.width), int(raw.height)
    solution = raw.solution
    if isinstance(solution, bytes):
        solution = solution.decode("ascii")
    if len(solution) != width * height:
        raise ValueError(f"Invalid solution length for {spec['id']}")

    grid = []
    for r in range(height):
        row = solution[r * width:(r + 1) * width]
        cells = []
        for char in row:
            char = char.upper()
            if char in {".", "#"}:
                cells.append("#")
            elif "A" <= char <= "Z":
                cells.append(".")
            else:
                raise ValueError(f"Unsupported solution cell {char!r} in {spec['id']}; rebus/unknown grids need explicit handling")
        grid.append("".join(cells))

    clues: dict[str, str] = {}
    answers: dict[str, str] = {}
    numbering = raw.clue_numbering()
    for direction, records in (("A", numbering.across), ("D", numbering.down)):
        stride = 1 if direction == "A" else width
        for record in records:
            clue_id = f"{int(record['num'])}{direction}"
            clue_index = int(record["clue_index"])
            clue = raw.clues[clue_index].strip()
            if not clue:
                raise ValueError(f"Missing text for {clue_id} in {spec['id']}")
            start = int(record["cell"])
            length = int(record["len"])
            answer = "".join(solution[start + i * stride] for i in range(length)).upper()
            if len(answer) != length or any(char not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ" for char in answer):
                raise ValueError(f"Invalid gold answer for {spec['id']} {clue_id}")
            clues[clue_id] = clue
            answers[clue_id] = answer

    item = {
        "id": spec["id"],
        "title": spec["title"],
        "date": spec.get("date"),
        "kind": spec.get("kind", "standard"),
        "source_author": manifest["author"],
        "source_archive": manifest["archive_url"],
        "source_puzzle_url": spec["url"],
        "license": manifest["license"],
        "license_url": manifest["license_url"],
        "grid": grid,
        "clues": clues,
        "answers": answers,
    }

    # Validate that the Across Lite numbering and solution map to this solver's
    # conventional grid representation before the item enters the gold corpus.
    sys.path.insert(0, str(ROOT))
    from src.crossword import Crossword
    puzzle = Crossword.from_dict(item)
    if set(puzzle.entries) != set(answers):
        raise ValueError(f"Entry-ID mismatch for {spec['id']}")
    for entry_id, entry in puzzle.entries.items():
        if len(answers[entry_id]) != entry.length:
            raise ValueError(f"Answer length mismatch for {spec['id']} {entry_id}")
    for a, ia, b, ib in puzzle.crossings:
        if answers[a][ia] != answers[b][ib]:
            raise ValueError(f"Gold crossing mismatch in {spec['id']}: {a} / {b}")
    return item


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--force", action="store_true", help="re-download source .puz files")
    parser.add_argument("--noncommercial-use", action="store_true", help="acknowledge the CC BY-NC-SA 4.0 noncommercial restriction")
    args = parser.parse_args()
    if not args.noncommercial_use:
        parser.error("The source puzzles are CC BY-NC-SA 4.0; pass --noncommercial-use only if your evaluation is non-commercial.")

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    args.output.mkdir(parents=True, exist_ok=True)
    raw_dir = args.output / "raw"
    items = []
    seen: set[str] = set()
    for spec in manifest["puzzles"]:
        if spec["id"] in seen:
            raise ValueError(f"Duplicate puzzle ID: {spec['id']}")
        seen.add(spec["id"])
        raw_path = raw_dir / f"{spec['id']}.puz"
        download(spec["url"], raw_path, force=args.force)
        item = convert_puzzle(spec, raw_path, manifest)
        items.append(item)
        print(f"OK {item['id']}: {len(item['grid'][0])}x{len(item['grid'])}, {len(item['answers'])} entries")

    dataset_path = args.output / "gold.json"
    dataset_path.write_text(json.dumps(items, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    notice = (
        f"Source puzzles by {manifest['author']} via {manifest['publisher']}\n"
        f"Archive: {manifest['archive_url']}\n"
        f"License: {manifest['license']} ({manifest['license_url']})\n"
        "Local-only benchmark output. Non-commercial use only; provide attribution and apply the same license to adaptations if redistributed.\n"
    )
    (args.output / "ATTRIBUTION.txt").write_text(notice, encoding="utf-8")
    print(f"Prepared {len(items)} puzzles at {dataset_path} (not included in the source repository).")


if __name__ == "__main__":
    main()
