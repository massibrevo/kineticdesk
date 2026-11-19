"""Offline synthetic replay benchmark. Reports CPU cost, never webcam accuracy."""
import argparse
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from kineticdesk.gestures import GestureEngine, Hand  # noqa: E402
from kineticdesk.replay import demo  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--replay", type=Path, default=Path("tests/fixtures"))
    parser.add_argument("--runs", type=int, default=100)
    args = parser.parse_args()
    if not (args.replay / "README.md").is_file() or args.runs < 1:
        parser.error("Use --replay tests/fixtures/ and a positive number of runs.")
    elapsed = []
    actions = Counter()
    data = [demo(i / 30) for i in range(145)]
    for _ in range(args.runs):
        engine = GestureEngine()
        for i, points in enumerate(data):
            start = time.perf_counter_ns()
            events = engine.tick(i / 30, Hand.from_points(points))
            elapsed.append((time.perf_counter_ns() - start) / 1_000)
            actions.update(a.kind for a in events)
        assert engine.reason == "palm"
    p95 = sorted(elapsed)[int(.95 * (len(elapsed) - 1))]
    print(f"Synthetic landmarks: {len(elapsed)} frames, {args.runs} scripted sessions")
    print(f"Geometry + gesture engine: median {statistics.median(elapsed):.2f} µs, p95 {p95:.2f} µs")
    print(f"Actions per replay: {dict((k, v // args.runs) for k, v in actions.items())}")


if __name__ == "__main__":
    main()
