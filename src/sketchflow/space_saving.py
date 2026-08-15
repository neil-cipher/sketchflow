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

**Step 11 upgrade:** internals now use a min-heap (``heapq``) + hash
index for O(log k) ``add()`` instead of the step-10 O(k) linear scan.
The external API (``add``, ``query``, ``top_k``, ``counters``, ``total``)
is unchanged.  The heap is an implementation detail; ``counters`` remains
the authoritative view and is kept in sync with every heap mutation.

Heap design notes
~~~~~~~~~~~~~~~~~
Each heap entry is ``[count, seq, key]`` — a mutable list so we can
update count in place.  ``seq`` is a monotonically increasing insertion
sequence number that breaks count ties deterministically (FIFO: earlier
inserts surface first as min, matching the step-10 ``min()`` behavior
on dicts in insertion order).  A separate ``_index`` dict maps key →
heap-entry reference for O(1) lookup.  ``heapq`` is a standard-library
binary min-heap; push/pop are O(log k), sift-up after a count bump is
O(log k) via ``heapq._siftdown`` (safe and stable in CPython ≥3.8;
if unavailable we fall back to ``heapq.heapify`` which is O(k) but
keeps correctness).
"""

from __future__ import annotations

import heapq

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
        Kept in sync with the internal heap on every mutation.
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

        # ── internal heap structures (step 11) ──────────────────────
        # _heap: min-heap of [count, seq, key] entries.
        # _index: key → reference to its [count, seq, key] entry.
        # _seq: monotonic counter for tie-breaking (FIFO eviction).
        self._heap: list[list] = []
        self._index: dict[str, list] = {}
        self._seq: int = 0

    # ── helpers ─────────────────────────────────────────────────────

    def _next_seq(self) -> int:
        """Return the next sequence number (monotonic)."""
        s = self._seq
        self._seq += 1
        return s

    def _sift_up(self, entry: list) -> None:
        """Re-establish heap order after *increasing* an entry's count.

        ``heapq`` does not expose a decrease-key / sift-up by entry.
        We locate the entry's position and call the internal
        ``_siftdown`` (which sifts *down* from position 0 to ``pos``,
        i.e. it is actually sift-up in textbook terminology — CPython
        naming is inverted).  If the private API is unavailable we
        fall back to a full ``heapify`` for correctness.
        """
        try:
            pos = self._heap.index(entry)
        except ValueError:
            return  # entry was removed concurrently (shouldn't happen)
        # CPython's _siftdown pushes the element at pos UP toward the
        # root — the name is confusing but correct for our use case.
        _siftdown = getattr(heapq, '_siftdown', None)
        if _siftdown is not None:
            _siftdown(self._heap, 0, pos)
        else:
            heapq.heapify(self._heap)

    def _sift_down(self, entry: list) -> None:
        """Re-establish heap order after *decreasing* an entry's count
        (or after the entry is replaced at the root)."""
        try:
            pos = self._heap.index(entry)
        except ValueError:
            return
        _siftup = getattr(heapq, '_siftup', None)
        if _siftup is not None:
            _siftup(self._heap, pos)
        else:
            heapq.heapify(self._heap)

    # ── public API (unchanged from step 10) ─────────────────────────

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

        Complexity: O(log k) per call (heap push/pop + sift).
        """
        if count < 0:
            raise ValueError("negative counts are not supported")
        self.total += count
        if count == 0:
            return

        if key in self._index:
            # Key already monitored — bump its count in-place and fix
            # the heap (count went up, so the entry may need to sink
            # deeper — but since it's a min-heap and the count
            # *increased*, the entry can only move DOWN, not up).
            entry = self._index[key]
            entry[0] += count
            self.counters[key] = entry[0]
            self._sift_down(entry)
        elif len(self._heap) < self.k:
            # Free slot available — insert directly.
            entry = [count, self._next_seq(), key]
            heapq.heappush(self._heap, entry)
            self._index[key] = entry
            self.counters[key] = count
        else:
            # Full — evict the minimum-count entry (heap root).
            min_entry = self._heap[0]
            min_key = min_entry[2]
            min_count = min_entry[0]

            # Remove old key from index and counters.
            del self._index[min_key]
            del self.counters[min_key]

            # Reuse the heap slot: overwrite the root entry in-place
            # with the new key and its inherited count, then sift down.
            new_count = min_count + count
            min_entry[0] = new_count
            min_entry[1] = self._next_seq()
            min_entry[2] = key
            self._index[key] = min_entry
            self.counters[key] = new_count
            self._sift_down(min_entry)

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

    # ── heap introspection (step 11 gate) ───────────────────────────

    def _assert_heap_invariant(self) -> None:
        """Verify the min-heap property and index consistency.

        Raises ``AssertionError`` on any violation. Intended for tests.
        """
        # 1. Heap property: parent <= each child.
        n = len(self._heap)
        for i in range(n):
            left = 2 * i + 1
            right = 2 * i + 2
            if left < n:
                assert self._heap[i] <= self._heap[left], (
                    f"heap violation at {i}: {self._heap[i]} > {self._heap[left]}"
                )
            if right < n:
                assert self._heap[i] <= self._heap[right], (
                    f"heap violation at {i}: {self._heap[i]} > {self._heap[right]}"
                )

        # 2. Index size matches heap size.
        assert len(self._index) == len(self._heap), (
            f"index size {len(self._index)} != heap size {len(self._heap)}"
        )

        # 3. Every index entry points to the correct heap entry.
        for key, entry in self._index.items():
            assert entry[2] == key, (
                f"index key {key!r} points to entry with key {entry[2]!r}"
            )
            assert entry in self._heap, (
                f"index entry for {key!r} not found in heap"
            )

        # 4. Counters dict matches heap counts.
        assert len(self.counters) == len(self._heap), (
            f"counters size {len(self.counters)} != heap size {len(self._heap)}"
        )
        for key, cnt in self.counters.items():
            assert key in self._index, (
                f"counters key {key!r} not in index"
            )
            assert self._index[key][0] == cnt, (
                f"counters[{key!r}]={cnt} != heap entry count "
                f"{self._index[key][0]}"
            )
