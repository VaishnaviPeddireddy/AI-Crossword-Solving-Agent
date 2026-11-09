from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from src.crossword import Crossword
from src.evaluator import evaluate, evaluate_compare
from src.llm import DemoProvider, OpenAICompatibleProvider
from src.solver import solve


def load_dotenv(path: Path = ROOT / ".env") -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Constraint-driven crossword solving agent")
    parser.add_argument("--puzzle", default="data/sample_puzzles.json", help="JSON puzzle or benchmark dataset")
    parser.add_argument("--provider", choices=["demo", "api"], default="demo")
    parser.add_argument("--strategy", choices=["baseline", "constraints", "agent"], default="agent")
    parser.add_argument("--evaluate", action="store_true", help="Evaluate the dataset with the selected strategy")
    parser.add_argument("--compare", action="store_true", help="Compare baseline, constraints, and full agent")
    parser.add_argument("--json", action="store_true", help="Print evaluation output as JSON")
    args = parser.parse_args()
    if args.evaluate or args.compare:
        provider_factory = DemoProvider if args.provider == "demo" else OpenAICompatibleProvider
        if args.compare:
            report = evaluate_compare(args.puzzle, provider_factory)
            if args.json:
                print(json.dumps(report, indent=2))
            else:
                generation = report["candidate_generation"]
                print(f"Evaluation on {generation['puzzles']} gold-labelled puzzle(s); initial candidate lists are shared across solver arms.")
                print(f"{'Strategy':<14} {'Word':>8} {'Letter':>8} {'Exact':>8} {'Backtracks':>11}")
                for row in report["strategies"]:
                    print(f"{row['strategy']:<14} {row['word_accuracy']:>7.1%} {row['letter_accuracy']:>7.1%} {row['full_puzzle_solve_rate']:>7.1%} {row['avg_backtracks']:>11.1f}")
                print(f"Candidate generation: model={generation['model'] or generation['provider']}, calls={generation['calls']}, tokens={generation['input_tokens']} in / {generation['output_tokens']} out, latency={generation['latency_seconds']:.2f}s, failures={len(generation['failures'])}")
                print("Cost: not reported until a dated provider/model rate card is verified.")
        else:
            report = evaluate(args.puzzle, args.strategy, provider_factory)
            if args.json:
                print(json.dumps(report, indent=2))
            else:
                print(f"Evaluation on {report['puzzles']} gold-labelled puzzle(s)")
                print(f"{report['strategy']}: word={report['word_accuracy']:.1%}, letter={report['letter_accuracy']:.1%}, exact={report['full_puzzle_solve_rate']:.1%}, calls={report['avg_api_calls']:.1f}/puzzle, latency={report['avg_latency_seconds']:.3f}s/puzzle, failures={len(report['failures'])}")
                print("Cost: not reported until a dated provider/model rate card is verified.")
        return

    payload = json.loads(Path(args.puzzle).read_text())
    item = payload[0] if isinstance(payload, list) else payload
    puzzle = Crossword.from_dict(item)
    provider = DemoProvider() if args.provider == "demo" else OpenAICompatibleProvider()
    result = solve(puzzle, provider, args.strategy)
    print("CROSSWORD AGENT  |  semantic candidates + deterministic constraint solving")
    print("\nGrid before:\n" + puzzle.render())
    print("\nCandidate proposals")
    for event in result.events:
        if event["type"] == "candidates":
            choices = ", ".join(f"{word} ({score:.2f})" for word, score in event["answers"])
            print(f"  {event['entry']:>3}  {puzzle.entries[event['entry']].clue:<26} pattern={event['pattern']}  {choices}")
        elif event["type"] == "prune":
            print(f"  PRUNE {event['entry']}={event['answer']} — conflicts with {event['crossing']} at a crossing")
        elif event["type"] == "regenerate":
            choices = ", ".join(f"{word} ({score:.2f})" for word, score in event["answers"])
            print(f"  REQUERY {event['entry']} with pattern {event['pattern']} → {choices or 'no candidates'}")
        elif event["type"] == "try":
            print(f"  TRY   {event['entry']}={event['answer']} ({event['confidence']:.2f})")
        elif event["type"] == "backtrack":
            print(f"  UNDO  {event['entry']}={event['answer']} — downstream contradiction")
    print("\nGrid after:\n" + puzzle.render(result.answers))
    print(f"\nStatus: {'SOLVED ✓' if result.solved else 'UNSOLVED / INCONSISTENT'}")
    print(f"Entries: {len(result.answers)}/{len(puzzle.entries)} | Provider calls: {provider.calls} | Backtracks: {result.backtracks} | Latency: {provider.elapsed_seconds:.4f}s")
    if args.provider == "api":
        print(f"Tokens: {provider.input_tokens} input / {provider.output_tokens} output")


if __name__ == "__main__":
    main()
