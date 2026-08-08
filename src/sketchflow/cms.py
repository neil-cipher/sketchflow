"""Count-Min Sketch — the hero structure (skeleton, step 5).

A CMS is a depth x width matrix of integer counters. Each of the
``depth`` rows gets its own hash function from the step-2 tabulation
family; ``add(key)`` increments exactly one counter per row (the one
the row's hash picks). Collisions can only ADD strangers' counts on
top of yours — a counter is the sum of every key that lands in it —
so every counter touched by a key is >= that key's true count.

That is the *never-undercount invariant*, and it is the foundation
the ε/δ guarantee (step 6: query = min over rows + sizing) rests on.

Reference: Cormode & Muthukrishnan, "An improved data stream summary:
the count-min sketch and its applications", J. Algorithms 55 (2005).
"""

from __future__ import annotations

from sketchflow.hashing import HashFamily

__all__ = ["CountMinSketch"]


class CountMinSketch:
    """Skeleton: counter matrix + add(). The min-query and the
    ε/δ-driven sizing land in step 6."""

    def __init__(self, width: int = 1024, depth: int = 4, seed: int = 42):
        if width < 1 or depth < 1:
            raise ValueError(f"width and depth must be >= 1, got {width}x{depth}")
        self.width = width
        self.depth = depth
        self.seed = seed
        # depth independent hash functions, each mapped onto [0, width)
        self.family = HashFamily(k=depth, width=width, seed=seed)
        # depth rows x width counters, all zero
        self.rows = [[0] * width for _ in range(depth)]
        self.total = 0  # N: number of add() calls (stream length)

    def add(self, key: str, count: int = 1) -> None:
        """Count one occurrence (or ``count``) of ``key``: bump the
        single hashed counter in each row."""
        if count < 0:
            raise ValueError("negative counts are not supported")
        for row, bucket in zip(self.rows, self.family.buckets(key)):
            row[bucket] += count
        self.total += count

    def row_values(self, key: str) -> list[int]:
        """The ``depth`` counters that ``key`` hashes to — every one of
        them is an overestimate (>= the key's true count)."""
        return [
            row[bucket]
            for row, bucket in zip(self.rows, self.family.buckets(key))
        ]
