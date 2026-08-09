"""Count-Min Sketch — the hero structure.

A CMS is a depth x width matrix of integer counters. Each of the
``depth`` rows gets its own hash function from the step-2 tabulation
family; ``add(key)`` increments exactly one counter per row (the one
the row's hash picks). Collisions can only ADD strangers' counts on
top of yours — a counter is the sum of every key that lands in it —
so every counter touched by a key is >= that key's true count.

That is the *never-undercount invariant*, and it is the foundation
the ε/δ guarantee rests on.

**Step 5** built the skeleton: counter matrix + ``add()`` + ``row_values()``.

**Step 6** adds the min-query estimator and the ε/δ ↔ (width, depth)
sizing calculator. The point query ``query(key)`` returns the minimum
counter across all rows — the tightest overestimate. The additive
error bound guarantees:

    query(key) − true(key) ≤ ε · N   with probability ≥ 1 − δ

when width = ⌈e/ε⌉ and depth = ⌈ln(1/δ)⌉ (Cormode & Muthukrishnan 2005,
Theorem 1). ``size_cms(epsilon, delta)`` computes those parameters.

Reference: Cormode & Muthukrishnan, "An improved data stream summary:
the count-min sketch and its applications", J. Algorithms 55 (2005).
"""

from __future__ import annotations

import math

from sketchflow.hashing import HashFamily

__all__ = ["CountMinSketch", "size_cms"]


class CountMinSketch:
    """A depth × width counter matrix that estimates item frequencies
    in a data stream with bounded additive error.

    The ``query()`` method (step 6) returns the minimum counter across
    all rows — guaranteed to lie in [true_count, true_count + ε·N]
    with probability ≥ 1−δ when sized via ``size_cms(epsilon, delta)``.
    """

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

    def query(self, key: str) -> int:
        """Point-query estimate for ``key``: the minimum counter across
        all ``depth`` rows.

        Because collisions only inflate, every row's counter is an
        overestimate.  Taking the minimum gives the tightest one.
        The ε/δ guarantee says this value exceeds the true count by
        at most ε·N with probability ≥ 1−δ (when sized properly).
        """
        return min(self.row_values(key))

    def row_values(self, key: str) -> list[int]:
        """The ``depth`` counters that ``key`` hashes to — every one of
        them is an overestimate (>= the key's true count)."""
        return [
            row[bucket]
            for row, bucket in zip(self.rows, self.family.buckets(key))
        ]


def size_cms(epsilon: float, delta: float) -> tuple[int, int]:
    """Compute CMS dimensions from the error-bound parameters.

    Returns ``(width, depth)`` such that a CMS with these dimensions
    guarantees, for every key:

        query(key) − true_count(key) ≤ ε · N   with prob ≥ 1 − δ

    where N is the stream length.

    The standard sizing (Cormode & Muthukrishnan 2005, Theorem 1):

        width  = ⌈ e / ε ⌉     (e = 2.71828…)
        depth  = ⌈ ln(1/δ) ⌉

    Parameters
    ----------
    epsilon : float
        Additive error fraction, in (0, 1).  Smaller ε → wider table
        → more memory → tighter estimates.
    delta : float
        Failure probability, in (0, 1).  Smaller δ → deeper table
        → more hash functions → higher success probability.

    Raises
    ------
    ValueError
        If epsilon or delta is outside (0, 1).
    """
    if not (0.0 < epsilon < 1.0):
        raise ValueError(f"epsilon must be in (0, 1), got {epsilon}")
    if not (0.0 < delta < 1.0):
        raise ValueError(f"delta must be in (0, 1), got {delta}")
    width = math.ceil(math.e / epsilon)
    depth = math.ceil(math.log(1.0 / delta))
    return width, depth
