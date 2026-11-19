"""Deterministic, synthetic 21-landmark sequences. Coordinates are not recordings."""
import json
from functools import lru_cache
from pathlib import Path


@lru_cache
def poses():
    path = Path(__file__).with_name("replay_poses.json")
    return json.loads(path.read_text())


TIMELINE = [
    (0, "fist", 0, 0), (.90, "point", -.11, -.08), (1.24, "point", .05, .07),
    (1.48, "pinch", .05, .07), (1.68, "point", .05, .07), (1.90, "point", .12, .12),
    (1.99, "pinch", .12, .12), (2.52, "pinch", .12, .12),
    (3.10, "pinch", .29, -.035), (3.25, "point", .29, -.035),
    (3.48, "scroll", .01, -.12), (3.71, "scroll", .01, -.12),
    (4.08, "scroll", .01, .06), (4.40, "palm", 0, 0),
    (4.85, "palm", 0, 0),
]


def frame(name, x=0., y=0.):
    return [[px + x, py + y, pz] for px, py, pz in poses()[name]]


def demo(elapsed):
    for left, right in zip(TIMELINE, TIMELINE[1:]):
        start, name, x, y = left
        end, next_name, next_x, next_y = right
        if elapsed < end:
            if name == next_name:
                fraction = (elapsed - start) / (end - start)
                return frame(name, x + fraction * (next_x - x), y + fraction * (next_y - y))
            return frame(name, x, y)
    return None
