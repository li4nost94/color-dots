#!/usr/bin/env python3
"""Generate small Flow-style levels: orthogonal paths, pairs connect, full board fill."""
from __future__ import annotations

import json
import random
from dataclasses import dataclass
from typing import List, Optional, Tuple

Coord = Tuple[int, int]


def neighbors(n: int, r: int, c: int) -> List[Coord]:
    out = []
    if r > 0:
        out.append((r - 1, c))
    if r < n - 1:
        out.append((r + 1, c))
    if c > 0:
        out.append((r, c - 1))
    if c < n - 1:
        out.append((r, c + 1))
    return out


def try_pack(
    n: int,
    num_colors: int,
    rng: random.Random,
    attempts: int = 4000,
) -> Optional[Tuple[List[List[int]], List[Tuple[Coord, Coord]]]]:
    """
    Randomized 'snake growing' packer inspired by simple Flow generators.
    Returns (grid color ids 0..k-1, list of (start,end) per color) or None.
    """
    for _ in range(attempts):
        grid = [[-1] * n for _ in range(n)]
        endpoints: List[Tuple[Coord, Coord]] = []

        def free_cells() -> List[Coord]:
            return [(r, c) for r in range(n) for c in range(n) if grid[r][c] == -1]

        if not free_cells():
            continue

        ok = True
        for color in range(num_colors):
            cells = free_cells()
            if not cells:
                ok = False
                break
            sr, sc = rng.choice(cells)

            path: List[Coord] = [(sr, sc)]
            grid[sr][sc] = color
            length_target = max(2, (n * n - sum(1 for r in range(n) for c in range(n) if grid[r][c] != -1)) // (num_colors - color))

            grow = True
            while grow:
                grow = False
                r, c = path[-1]
                opts = [p for p in neighbors(n, r, c) if grid[p[0]][p[1]] == -1]
                rng.shuffle(opts)
                for nr, nc in opts:
                    # bias: don't seal off tiny pockets if avoidable
                    path.append((nr, nc))
                    grid[nr][nc] = color
                    grow = True
                    break

            # ensure at least 2 cells; set endpoints as path ends
            if len(path) < 2:
                ok = False
                break
            endpoints.append((path[0], path[-1]))

        if not ok:
            continue
        if any(grid[r][c] == -1 for r in range(n) for c in range(n)):
            continue
        return grid, endpoints
    return None


def grid_to_level(
    name: str,
    grid: List[List[int]],
    endpoints: List[Tuple[Coord, Coord]],
    palette: List[str],
) -> dict:
    n = len(grid)
    pairs = []
    for i, (a, b) in enumerate(endpoints):
        col = palette[i % len(palette)]
        pairs.append(
            {
                "id": i,
                "color": col,
                "start": [a[0], a[1]],
                "end": [b[0], b[1]],
            }
        )
    return {"name": name, "size": n, "pairs": pairs, "solution": grid}


def main() -> None:
    rng = random.Random(42)
    palette = [
        "#FF2D95",
        "#00E5FF",
        "#B388FF",
        "#69F0AE",
        "#FFEA00",
        "#FF5252",
        "#FF9100",
        "#40C4FF",
    ]
    levels = []
    specs = [
        ("Tutorial", 4, 3),
        ("Neon Start", 5, 4),
        ("Glow Grid", 5, 5),
        ("Think Fast", 6, 5),
        ("Brain Burn", 6, 6),
        ("Master Link", 6, 7),
    ]
    seed = 42
    for name, n, k in specs:
        rng = random.Random(seed)
        seed += 1
        packed = None
        for _ in range(20000):
            packed = try_pack(n, k, rng, attempts=1)
            if packed:
                break
        if not packed:
            raise SystemExit(f"failed {name}")
        grid, ep = packed
        levels.append(grid_to_level(name, grid, ep, palette))

    json_path = "../js/levels.generated.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(levels, f, ensure_ascii=False, indent=2)
    js_path = "../js/levels.data.js"
    with open(js_path, "w", encoding="utf-8") as f:
        f.write("window.COLOR_DOTS_LEVELS = ")
        json.dump(levels, f, ensure_ascii=False)
        f.write(";\n")
    print("wrote", json_path, js_path, "levels", len(levels))


if __name__ == "__main__":
    main()
