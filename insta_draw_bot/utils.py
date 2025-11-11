import math
from typing import Tuple, List


def color_distance(a: Tuple[int, int, int], b: Tuple[int, int, int]) -> float:
    r1, g1, b1 = a
    r2, g2, b2 = b
    return math.sqrt((r1 - r2) ** 2 + (g1 - g2) ** 2 + (b1 - b2) ** 2)


def find_nearest_color(target: Tuple[int, int, int], palette: List[Tuple[int, int, int]]):
    if not palette:
        return target
    best = palette[0]
    best_d = color_distance(target, best)
    for c in palette[1:]:
        d = color_distance(target, c)
        if d < best_d:
            best = c
            best_d = d
    return best


def clamp(v, a, b):
    return max(a, min(b, v))
