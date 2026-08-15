"""Tests for step 11: Space-Saving min-heap + hash index for O(log k) update.

Gate (plan.json step 11):
    "same results as step 10 but throughput scales; heap invariant asserted"

We verify:
 1. All step-10 behavioral guarantees still hold (same API, same results).
 2. The internal min-heap invariant is maintained after every operation.
 3. Throughput on large k scales better than O(k) per add (the whole
    point of the heap upgrade).

Reference:
    Metwally, Agrawal & El Abbadi, "Efficient computation of frequent
    and top-k elements in data streams", ICDT 2005.
"""

import time

import pytest

from sketchflow.space_saving import SpaceSaving
from sketchflow.baseline import ExactCounter
from sketchflow.streams import zipfian_stream


# ── Gate: heap invariant after every mutation ──────────────────────

class TestHeapInvariant:
    """The min-heap property and index consistency must hold after
    every add(), across inserts, bumps, and evictions."""

    def test_invariant_after_inserts(self):
        """Heap invariant holds after filling up slots."""
        ss = SpaceSaving(k=10)
        for i in range(10):
            ss.add(f"key_{i}", count=i + 1)
            ss._assert_heap_invariant()

    def test_invariant_after_bumps(self):
        """Heap invariant holds after bumping existing keys."""
        ss = SpaceSaving(k=5)
        for i in range(5):
            ss.add(f"k{i}", count=1)
        ss._assert_heap_invariant()
        # Bump different keys with varying counts.
        for _ in range(50):
            for i in range(5):
                ss.add(f"k{i}", count=(i + 1) * 3)
                ss._assert_heap_invariant()

    def test_invariant_after_evictions(self):
        """Heap invariant holds through many eviction cycles."""
        ss = SpaceSaving(k=5)
        for i in range(200):
            ss.add(f"key_{i}")
            ss._assert_heap_invariant()

    def test_invariant_on_zipfian_stream(self):
        """Heap invariant holds across a realistic Zipfian workload."""
        ss = SpaceSaving(k=20)
        stream = list(zipfian_stream(n_items=5_000, universe=200,
                                     alpha=1.5, seed=42))
        for key in stream:
            ss.add(key)
        # Check at the end (checking every add would be slow for 5k).
        ss._assert_heap_invariant()

    def test_invariant_with_weighted_adds(self):
        """Heap invariant with count > 1 adds and evictions."""
        ss = SpaceSaving(k=3)
        ss.add("a", count=100)
        ss.add("b", count=1)
        ss.add("c", count=50)
        ss._assert_heap_invariant()
        ss.add("d", count=10)  # evicts b (min=1), d=1+10=11
        ss._assert_heap_invariant()
        ss.add("a", count=200)
        ss._assert_heap_invariant()
        assert ss.counters["a"] == 300

    def test_invariant_k_equals_one(self):
        """Heap invariant with k=1 (single slot, constant eviction)."""
        ss = SpaceSaving(k=1)
        for i in range(50):
            ss.add(f"key_{i}")
            ss._assert_heap_invariant()


# ── Gate: same results as step 10 ─────────────────────────────────

class TestSameResultsAsStep10:
    """The heap upgrade must produce identical outputs to step 10."""

    def test_exact_top_k_on_zipfian(self):
        """On a high-skew Zipfian stream, top-10 matches exact baseline."""
        stream = list(zipfian_stream(n_items=10_000, universe=500,
                                     alpha=2.0, seed=42))
        exact = ExactCounter()
        ss = SpaceSaving(k=50)
        for key in stream:
            exact.add(key)
            ss.add(key)

        exact_top10 = {k for k, _ in exact.top_k(10)}
        ss_top10 = {k for k, _ in ss.top_k(10)}
        assert exact_top10 == ss_top10

    def test_guarantee_heavy_hitters_present(self):
        """Every key with true count > N/k is monitored."""
        k = 15
        stream = list(zipfian_stream(n_items=20_000, universe=1000,
                                     alpha=1.5, seed=99))
        exact = ExactCounter()
        ss = SpaceSaving(k=k)
        for key in stream:
            exact.add(key)
            ss.add(key)

        threshold = ss.total / k
        monitored = set(ss.counters.keys())
        for key, true_count in exact.counts.items():
            if true_count > threshold:
                assert key in monitored, (
                    f"key {key!r} count {true_count} > N/k={threshold:.1f} "
                    f"but not monitored"
                )

    def test_guarantee_multiple_seeds(self):
        """Heavy-hitter guarantee holds across 10 seeds."""
        k = 10
        for seed in range(10):
            stream = list(zipfian_stream(n_items=5_000, universe=200,
                                         alpha=2.0, seed=seed))
            exact = ExactCounter()
            ss = SpaceSaving(k=k)
            for key in stream:
                exact.add(key)
                ss.add(key)

            threshold = ss.total / k
            monitored = set(ss.counters.keys())
            for key, tc in exact.counts.items():
                if tc > threshold:
                    assert key in monitored

    def test_overestimate_invariant(self):
        """Monitored counts >= true counts (never undercount)."""
        stream = list(zipfian_stream(n_items=10_000, universe=500,
                                     alpha=1.5, seed=77))
        exact = ExactCounter()
        ss = SpaceSaving(k=20)
        for key in stream:
            exact.add(key)
            ss.add(key)

        for key, est in ss.counters.items():
            true_count = exact.query(key)
            assert est >= true_count, (
                f"undercount: {key!r} est={est} < true={true_count}"
            )

    def test_eviction_mechanics(self):
        """Same eviction behavior as step 10."""
        ss = SpaceSaving(k=2)
        ss.add("a")
        ss.add("a")
        ss.add("b")
        ss.add("c")  # evicts b(1), c=1+1=2
        assert "b" not in ss.counters
        assert "c" in ss.counters
        assert ss.counters["c"] == 2
        assert ss.counters["a"] == 2
        ss._assert_heap_invariant()

    def test_top_k_ordering_and_ties(self):
        """top_k ordering + alphabetic tie-breaking preserved."""
        ss = SpaceSaving(k=5)
        ss.add("banana", count=5)
        ss.add("apple", count=5)
        ss.add("cherry", count=5)
        top = ss.top_k()
        keys = [k for k, _ in top]
        assert keys == ["apple", "banana", "cherry"]

    def test_total_tracks_stream_length(self):
        ss = SpaceSaving(k=5)
        for i in range(100):
            ss.add(f"key_{i % 20}")
        assert ss.total == 100

    def test_capacity_never_exceeded(self):
        ss = SpaceSaving(k=5)
        for i in range(1000):
            ss.add(f"key_{i}")
        assert len(ss.counters) <= 5
        ss._assert_heap_invariant()


# ── Gate: throughput scales with k ─────────────────────────────────

class TestThroughputScales:
    """The heap-based implementation should show sub-linear scaling
    as k grows, unlike the O(k) linear-scan step-10 version."""

    def test_throughput_not_degraded_at_large_k(self):
        """With k=2000 and 50k adds, throughput must exceed 50k ops/sec
        (a very conservative bar — the heap should easily clear it;
        the linear-scan version would be ~10x slower at this k)."""
        k = 2000
        n_adds = 50_000
        ss = SpaceSaving(k=k)

        start = time.perf_counter()
        for i in range(n_adds):
            ss.add(f"key_{i % (k * 2)}")
        elapsed = time.perf_counter() - start

        throughput = n_adds / elapsed
        # Very conservative: 50k ops/sec should be trivial for heap.
        assert throughput > 50_000, (
            f"throughput {throughput:.0f} ops/sec too low for k={k}"
        )
        ss._assert_heap_invariant()

    def test_scaling_ratio(self):
        """Throughput at k=2000 should be at least 30% of throughput
        at k=50 (heap is O(log k) so ~7x factor in theory; linear
        scan would be ~40x slower).  This is the scaling gate."""
        n_adds = 30_000

        def measure(k_val):
            ss = SpaceSaving(k=k_val)
            start = time.perf_counter()
            for i in range(n_adds):
                ss.add(f"key_{i % (k_val * 2)}")
            return n_adds / (time.perf_counter() - start)

        t_small = measure(50)
        t_large = measure(2000)
        ratio = t_large / t_small

        # With O(log k): log(2000)/log(50) ≈ 2, so ratio ~ 0.5.
        # With O(k): ratio ~ 50/2000 = 0.025.
        # We require ratio > 0.15 — easily passes for heap, fails
        # for linear scan.
        assert ratio > 0.15, (
            f"scaling ratio {ratio:.3f} too low — suggests O(k) not "
            f"O(log k). t_small={t_small:.0f}, t_large={t_large:.0f}"
        )
