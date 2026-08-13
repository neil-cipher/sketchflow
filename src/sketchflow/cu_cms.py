"""Conservative-Update Count-Min Sketch — less noise, same guarantees.

A standard CMS blindly increments every row's counter on ``add(key)``.
Conservative Update (CU) is smarter: it first checks the *current*
minimum counter across all rows (our best estimate of the true count),
then only bumps counters that are at or below that minimum.  Counters
that are already above the minimum are inflated by collisions — adding
to them would pile noise on top of noise — so CU leaves them alone.

The result: every CU counter is <= the corresponding plain-CMS counter
on the same stream, but the *never-undercount* invariant still holds.
The ε/δ guarantee is unchanged (conservative update can only reduce
error); in practice, CU cuts overestimation substantially, especially
for low-frequency items in skewed distributions.

Reference: Estan & Varghese, "New directions in traffic measurement
and accounting", SIGCOMM 2002, Section 4.2.  Also see Cormode &
Muthukrishnan 2005, Section 5.

**Step 9** of plan.json — built on step 8's CountMinSketch.
"""

from __future__ import annotations

import struct

from sketchflow.cms import CountMinSketch

__all__ = ["ConservativeUpdateCMS"]


class ConservativeUpdateCMS(CountMinSketch):
    """A Count-Min Sketch with conservative-update ``add()``.

    Inherits everything from :class:`CountMinSketch` (query, row_values,
    inner_product, memory accounting, serialization) — the only
    difference is that ``add()`` avoids inflating counters that are
    already above the current minimum estimate.

    Gate (step 9): for every key on the same stream, the CU estimate
    is ``<=`` the plain-CMS estimate, yet still ``>=`` the true count.
    """

    def add(self, key: str, count: int = 1) -> None:
        """Conservative-update add: only bump the lowest counters.

        Algorithm
        ---------
        1. Compute ``buckets`` — the column index in each row.
        2. Read the current counter value in each row.
        3. Find ``min_val`` — the current minimum across rows
           (our best estimate of the true count so far).
        4. For each row, set the counter to
           ``max(current, min_val + count)``.

        Counters already above ``min_val`` stay put — they are
        inflated by collisions, and adding to them would only
        increase overestimation.  Counters at or below ``min_val``
        are brought up to ``min_val + count``, which is exactly
        the new minimum after absorbing this occurrence.
        """
        if count < 0:
            raise ValueError("negative counts are not supported")
        buckets = self.family.buckets(key)
        # Read current counters for this key.
        current = [self.rows[d][buckets[d]] for d in range(self.depth)]
        min_val = min(current)
        target = min_val + count
        for d in range(self.depth):
            if current[d] < target:
                self.rows[d][buckets[d]] = target
        self.total += count

    # ── Deserialization override ──────────────────────────────────

    @classmethod
    def from_bytes(cls, data: bytes) -> "ConservativeUpdateCMS":
        """Reconstruct a CU-CMS from a ``to_bytes()`` blob.

        Same binary format as the parent — the CU property is a
        behavioural difference in ``add()``, not a storage difference.
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
            f"<{depth * width}Q", data[cls._HEADER_SIZE:]
        )
        for r in range(depth):
            for c in range(width):
                sketch.rows[r][c] = counters[r * width + c]
        return sketch
