"""Space-Saving top-k heavy hitter detection.

Keeps at most ``k`` monitored counters. When a new key arrives and all
``k`` slots are occupied, the entry with the **smallest** count is
evicted and its count is transferred to the new key (bumped by 1).
This guarantees that every key whose true frequency exceeds N/k will
be in the monitored set when the stream ends — the *Space-Saving
guarantee*.

The algorithm was introduced by:

    Metwally, Agrawal & El Abbadi, "Efficient computation of frequent
    and top-k elements in data streams", ICDT 2005.

This step-10 implementation uses a plain dict of monitored counters
and a linear scan for the minimum. Step 11 will upgrade the internals
to a min-heap + hash index for O(log k) update without changing the
external API.
"""

from __future__ import annotations

__all__ = ["SpaceSaving"]


class SpaceSaving:
    """Bounded-memory heavy hitter tracker using the Space-Saving algorithm.

    Parameters
    ----------
    k : int
        Maximum number of monitored counters (capacity). Must be >= 1.
        Larger k → more memory, but catches lighter hitters and gives
        tighter count estimates.

    Attributes
    ----------
    counters : dict[str, int]
        Monitored key → estimated count.  At most ``k`` entries.
    total : int
        Total items seen (the stream length N).

    Guarantee
    ---------
    After processing a stream of length N, every key with true count
    > N/k is present in ``counters``. The estimated count for a
    monitored key is always >= its true count (overestimate), and the
    overestimate error is at most the count of the evicted minimum
    at the time of insertion.
    """

    def __init__(self, k: int = 10):
        if k < 1:
            raise ValueError(f"k must be >= 1, got {k}")
        self.k = k
        self.counters: dict[str, int] = {}
        self.total = 0

    def add(self, key: str, count: int = 1) -> None:
        """Process one occurrence (or ``count`` occurrences) of ``key``.

        - If ``key`` is already monitored, its counter is bumped.
        - If there is a free slot (fewer than ``k`` entries), ``key``
          is inserted with the given ``count``.
        - Otherwise the entry with the smallest count is evicted and
          ``key`` takes its slot with count = evicted_min + ``count``.
          This is the core Space-Saving trick: the new key *inherits*
          the old minimum so the total across all counters stays
          consistent.
        """
        if count < 0:
            raise ValueError("negative counts are not supported")
        self.total += count
        if count == 0:
            return

        if key in self.counters:
            self.counters[key] += count
        elif len(self.counters) < self.k:
            self.counters[key] = count
        else:
            # Evict the minimum-count entry.
            min_key = min(self.counters, key=lambda k: self.counters[k])
            min_count = self.counters.pop(min_key)
            self.counters[key] = min_count + count

    def query(self, key: str) -> int:
        """Estimated count for ``key``.

        Returns the monitored counter if ``key`` is tracked, else 0.
        The estimate is always an overestimate (>= true count) for
        monitored keys. For unmonitored keys, the true count is at
        most the current minimum monitored count.
        """
        return self.counters.get(key, 0)

    def top_k(self, n: int | None = None) -> list[tuple[str, int]]:
        """Return the monitored keys sorted by estimated count (descending).

        Parameters
        ----------
        n : int or None
            How many to return. If ``None`` (default), returns all
            monitored entries (up to ``k``). If given, returns at most
            ``n`` entries.

        Returns
        -------
        list of (key, estimated_count) tuples, highest first.
        Ties are broken alphabetically by key for determinism.
        """
        items = sorted(
            self.counters.items(), key=lambda kv: (-kv[1], kv[0])
        )
        if n is not None:
            items = items[:n]
        return items
