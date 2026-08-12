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

**Step 7** adds honest memory accounting (``bytes_used()``) and compact
binary serialization (``to_bytes()`` / ``from_bytes()``).  The Python
in-memory cost of a list-of-lists of ints is far larger than the
mathematical minimum (depth × width × 8 bytes) — ``bytes_used()``
reports the real footprint via ``sys.getsizeof``, and the serialized
form shows what a C implementation would actually cost.

**Step 8** adds ``inner_product(other)`` — the join-size estimator.
Given two sketches built over different streams but sharing the same
hash functions, the inner product of their frequency vectors is
estimated as the minimum row-wise dot product of the counter arrays.
This is useful for join-size estimation, self-join (L2 norm squared),
and similarity queries between data streams.

Reference: Cormode & Muthukrishnan, "An improved data stream summary:
the count-min sketch and its applications", J. Algorithms 55 (2005).
"""

from __future__ import annotations

import math
import struct
import sys

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

    # ── Step 8: inner product / join-size estimate ─────────────────

    def inner_product(self, other: "CountMinSketch") -> int:
        """Estimate the inner product (dot product) of two frequency vectors.

        Given stream *a* counted in ``self`` and stream *b* counted in
        ``other``, the true inner product is:

            ⟨f_a, f_b⟩ = Σ_x  f_a(x) · f_b(x)

        This is the *join size* of the two streams — the number of
        matching pairs.  The CMS estimate (Cormode & Muthukrishnan 2005,
        Section 3) takes the **minimum** across rows of the per-row dot
        product of the counter arrays:

            estimate = min_d  Σ_j  A[d][j] · B[d][j]

        Because collisions only inflate individual counters, each row's
        dot product is an overestimate of the true inner product.  Taking
        the minimum gives the tightest one, and the error bound is:

            estimate − ⟨f_a, f_b⟩  ≤  ε · ‖a‖₁ · ‖b‖₁

        with probability ≥ 1 − δ, where ‖a‖₁ and ‖b‖₁ are the stream
        lengths (``self.total`` and ``other.total``).

        Both sketches **must** use the same width, depth, and seed
        (i.e. the same hash functions) — otherwise the row-wise dot
        product is meaningless.

        Parameters
        ----------
        other : CountMinSketch
            The second sketch. Must share width, depth, and seed.

        Returns
        -------
        int
            The estimated inner product (always ≥ the true value).

        Raises
        ------
        ValueError
            If the two sketches have different dimensions or seeds.

        Reference
        ---------
        Cormode & Muthukrishnan, "An improved data stream summary:
        the count-min sketch and its applications", J. Algorithms 55
        (2005), Section 3.
        """
        if self.width != other.width or self.depth != other.depth:
            raise ValueError(
                f"dimension mismatch: {self.width}x{self.depth} vs "
                f"{other.width}x{other.depth}"
            )
        if self.seed != other.seed:
            raise ValueError(
                f"seed mismatch: {self.seed} vs {other.seed} — both "
                f"sketches must share the same hash functions"
            )
        return min(
            sum(a * b for a, b in zip(row_a, row_b))
            for row_a, row_b in zip(self.rows, other.rows)
        )

    # ── Step 7: memory accounting ─────────────────────────────────

    def bytes_used(self) -> int:
        """Actual Python memory footprint of the counter matrix.

        Walks ``self.rows`` with ``sys.getsizeof`` to measure what the
        interpreter really allocated — outer list + each inner list +
        every integer object.  This is deliberately honest: a Python
        list-of-lists-of-ints is far heavier than a packed C array
        (typically ~4× on CPython for small counters).  The gap matters
        when comparing sketch memory against an exact ``dict`` baseline.
        """
        total = sys.getsizeof(self.rows)           # outer list header
        for row in self.rows:
            total += sys.getsizeof(row)             # inner list header
            for cell in row:
                total += sys.getsizeof(cell)        # int object
        return total

    # ── Step 7: serialization ─────────────────────────────────────

    _HEADER_FMT = "<IIqQ"   # width(u32) depth(u32) seed(i64) total(u64)
    _HEADER_SIZE = struct.calcsize(_HEADER_FMT)   # 24 bytes

    def to_bytes(self) -> bytes:
        """Serialize to a compact binary blob.

        Layout (little-endian, row-major):

            24 bytes   header  (width · depth · seed · total)
            depth × width × 8  counters  (each uint64)

        The packed size equals ``24 + depth * width * 8`` — the
        mathematical minimum for 64-bit counters.  Compare with
        ``bytes_used()`` to see the Python overhead.
        """
        header = struct.pack(self._HEADER_FMT,
                             self.width, self.depth, self.seed, self.total)
        # Pack all counters row-major as uint64.
        counters = struct.pack(
            f"<{self.depth * self.width}Q",
            *(cell for row in self.rows for cell in row),
        )
        return header + counters

    @classmethod
    def from_bytes(cls, data: bytes) -> "CountMinSketch":
        """Reconstruct a sketch from a ``to_bytes()`` blob.

        The hash family is re-seeded from the stored seed, so every
        query on the restored sketch returns the same result as the
        original — that is the round-trip guarantee step 7 tests.

        Raises
        ------
        ValueError
            If the blob is truncated or the wrong size.
        """
        if len(data) < cls._HEADER_SIZE:
            raise ValueError(
                f"blob too short for header: {len(data)} < {cls._HEADER_SIZE}"
            )
        width, depth, seed, total = struct.unpack(
            cls._HEADER_FMT, data[: cls._HEADER_SIZE]
        )
        expected = cls._HEADER_SIZE + depth * width * 8
        if len(data) != expected:
            raise ValueError(
                f"blob size mismatch: got {len(data)}, expected {expected}"
            )
        sketch = cls(width=width, depth=depth, seed=seed)
        sketch.total = total
        counters = struct.unpack(
            f"<{depth * width}Q", data[cls._HEADER_SIZE :]
        )
        for r in range(depth):
            for c in range(width):
                sketch.rows[r][c] = counters[r * width + c]
        return sketch


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
