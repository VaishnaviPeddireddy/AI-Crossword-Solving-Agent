from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Entry:
    id: str
    number: int
    direction: str
    clue: str
    cells: tuple[tuple[int, int], ...]

    @property
    def length(self) -> int:
        return len(self.cells)


class Crossword:
    """A crossword grid plus numbered Across/Down clues."""

    def __init__(self, rows: list[str], clues: dict[str, str]):
        if not rows or not rows[0]:
            raise ValueError("Grid must have at least one cell")
        width = len(rows[0])
        if any(len(row) != width for row in rows):
            raise ValueError("Grid rows must have equal width")
        if any(ch not in "#.?ABCDEFGHIJKLMNOPQRSTUVWXYZ" for row in rows for ch in row.upper()):
            raise ValueError("Grid cells must be #, ., ?, or letters")
        self.rows = [row.upper().replace("?", ".") for row in rows]
        self.height, self.width = len(rows), width
        self.clues = {key.upper(): value for key, value in clues.items()}
        self.entries: dict[str, Entry] = {}
        number = 0
        for r in range(self.height):
            for c in range(self.width):
                if self.rows[r][c] == "#":
                    continue
                across = c == 0 or self.rows[r][c - 1] == "#"
                down = r == 0 or self.rows[r - 1][c] == "#"
                if not (across or down):
                    continue
                number += 1
                for direction, starts in (("A", across), ("D", down)):
                    if not starts:
                        continue
                    dr, dc = (0, 1) if direction == "A" else (1, 0)
                    cells, rr, cc = [], r, c
                    while rr < self.height and cc < self.width and self.rows[rr][cc] != "#":
                        cells.append((rr, cc))
                        rr, cc = rr + dr, cc + dc
                    if len(cells) < 2:
                        continue
                    key = f"{number}{direction}"
                    if key not in self.clues:
                        raise ValueError(f"Missing clue for {key}")
                    self.entries[key] = Entry(key, number, direction, self.clues[key], tuple(cells))
        extra = set(self.clues) - set(self.entries)
        if extra:
            raise ValueError(f"Clues do not correspond to grid entries: {', '.join(sorted(extra))}")
        self.crossings: list[tuple[str, int, str, int]] = []
        cell_entries: dict[tuple[int, int], list[tuple[str, int]]] = {}
        for key, entry in self.entries.items():
            for index, cell in enumerate(entry.cells):
                cell_entries.setdefault(cell, []).append((key, index))
        for references in cell_entries.values():
            if len(references) == 2:
                (a, ia), (b, ib) = references
                self.crossings.append((a, ia, b, ib))
        self._cell_entries = cell_entries

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Crossword":
        return cls(data["grid"], data["clues"])

    def pattern(self, entry_id: str, answers: dict[str, str] | None = None) -> str:
        answers = answers or {}
        entry = self.entries[entry_id]
        letters: dict[tuple[int, int], str] = {}
        for other_id, word in answers.items():
            other = self.entries[other_id]
            letters.update({cell: word[i] for i, cell in enumerate(other.cells) if i < len(word)})
        return "".join(letters.get(cell, self.rows[cell[0]][cell[1]] if self.rows[cell[0]][cell[1]] != "." else "_") for cell in entry.cells)

    def render(self, answers: dict[str, str] | None = None) -> str:
        letters: dict[tuple[int, int], str] = {}
        for entry_id, word in (answers or {}).items():
            entry = self.entries[entry_id]
            for i, cell in enumerate(entry.cells):
                if i < len(word):
                    letters[cell] = word[i]
        out = []
        for r, row in enumerate(self.rows):
            cells = []
            for c, ch in enumerate(row):
                if ch == "#":
                    cells.append("■")
                else:
                    cells.append(letters.get((r, c), ch if ch != "." else "·"))
            out.append(" ".join(cells))
        return "\n".join(out)
