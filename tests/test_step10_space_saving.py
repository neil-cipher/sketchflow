"""Tests for step 10: Space-Saving top-k heavy hitter detection.

Gate (plan.json step 10):
    "reported top-k == exact top-k on a stream where heavy hitters
     exceed the 1/k threshold"

We test the Space-Saving guarantee: every key with true frequency > N/k
is present in the monitored set. We also verify overestimate behavior,
eviction mechanics, edge cases, and weighted adds.

Reference:
    Metwally, Agrawal & El Abbadi, "Efficient computation of frequent
    and top-k elements in data streams", ICDT 2005.
"""

from sketchflow.space_saving import SpaceSaving
from sketchflow.baseline import ExactCounter
from sketchflow.streams import zipfian_stream

import pytest


# ── Gate test: top-k matches exact on heavy-hitter stream ───────────

class TestSpaceSavingGate:
    """The core gate: top-k == exact top-k when heavy hitters > N/k."""

    def test_exact_top_k_on_zipfian(self):
        """On a high-skew Zipfian stream the true top-10 keys all have
        count well above N/k.  With k=50 monitored slots (generous
        headroom), Space-Saving must capture every one of them."""
        stream = list(zipfian_stream(n_items=10_000, universe=500, alpha=2.0, seed=42))
        exact = ExactCounter()
        ss = SpaceSaving(k=50)

        for key in stream:
            exact.add(key)
            ss.add(key)

        exact_top10_keys = {k for k, _ in exact.top_k(10)}
        monitored_keys = set(ss.counters.keys())
        missing = exact_top10_keys - monitored_keys
        assert not missing, (
            f"exact top-10 keys missing from monitored set: {missing}"
        )
        # Also: the SS top-10 must include every exact top-10 key.
        ss_top10_keys = {k for k, _ in ss.top_k(10)}
        assert exact_top10_keys == ss_top10_keys, (
            f"top-10 mismatch: exact={exact_top10_keys}, ss={ss_top10_keys}"
        )

    def test_guarantee_all_heavy_hitters_present(self):
        """The Space-Saving guarantee: every key with true count > N/k
        must be in the monitored set."""
        k = 15
        stream = list(zipfian_stream(n_items=20_000, universe=1000, alpha=1.5, seed=99))
        exact = ExactCounter()
        ss = SpaceSaving(k=k)

        for key in stream:
            exact.add(key)
            ss.add(key)

        threshold = ss.total / k
        monitored_keys = set(ss.counters.keys())

        for key, true_count in exact.counts.items():
            if true_count > threshold:
                assert key in monitored_keys, (
                    f"key {key!r} has true count {true_count} > N/k = "
                    f"{threshold:.1f} but is not monitored"
                )

    def test_multiple_seeds(self):
        """Gate holds across different stream seeds."""
        k = 10
        for seed in range(10):
            stream = list(zipfian_stream(n_items=5_000, universe=200, alpha=2.0, seed=seed))
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
                        f"seed={seed}: key {key!r} count {true_count} > "
                        f"N/k={threshold:.1f} missing"
                    )


# ── Never-undercount for monitored keys ─────────────────────────────

class TestOverestimate:
    """Monitored counts are always >= true counts (overestimate)."""

    def test_monitored_overestimate(self):
        """Every key in the monitored set has estimate >= true count."""
        stream = list(zipfian_stream(n_items=10_000, universe=500, alpha=1.5, seed=77))
        exact = ExactCounter()
        ss = SpaceSaving(k=20)

        for key in stream:
            exact.add(key)
            ss.add(key)

        for key, est_count in ss.counters.items():
            true_count = exact.query(key)
            assert est_count >= true_count, (
                f"undercount for {key!r}: estimate {est_count} < true {true_count}"
            )


# ── Basic mechanics ─────────────────────────────────────────────────

class TestBasicMechanics:
    """Unit tests for add/query/top_k behavior and eviction."""

    def test_single_key(self):
        ss = SpaceSaving(k=5)
        ss.add("a")
        ss.add("a")
        ss.add("a")
        assert ss.query("a") == 3
        assert ss.total == 3

    def test_fills_up_to_k(self):
        ss = SpaceSaving(k=3)
        ss.add("a")
        ss.add("b")
        ss.add("c")
        assert len(ss.counters) == 3
        assert ss.query("a") == 1
        assert ss.query("b") == 1
        assert ss.query("c") == 1

    def test_eviction_at_capacity(self):
        """When full, adding a new key evicts the minimum and inherits
        its count + 1."""
        ss = SpaceSaving(k=2)
        ss.add("a")       # a=1
        ss.add("a")       # a=2
        ss.add("b")       # b=1 (fills slot 2)
        # Now full with a=2, b=1
        ss.add("c")       # evicts b (min=1), c inherits 1+1=2
        assert "b" not in ss.counters
        assert "c" in ss.counters
        assert ss.counters["c"] == 2
        assert ss.counters["a"] == 2

    def test_unmonitored_returns_zero(self):
        ss = SpaceSaving(k=2)
        ss.add("a")
        assert ss.query("z") == 0

    def test_total_tracks_stream_length(self):
        ss = SpaceSaving(k=5)
        for i in range(100):
            ss.add(f"key_{i % 20}")
        assert ss.total == 100

    def test_top_k_ordering(self):
        ss = SpaceSaving(k=5)
        ss.add("a", count=10)
        ss.add("b", count=5)
        ss.add("c", count=8)
        top = ss.top_k()
        assert top[0] == ("a", 10)
        assert top[1] == ("c", 8)
        assert top[2] == ("b", 5)

    def test_top_k_with_n(self):
        ss = SpaceSaving(k=5)
        for i in range(5):
            ss.add(f"k{i}", count=(5 - i) * 10)
        top2 = ss.top_k(2)
        assert len(top2) == 2
        assert top2[0][0] == "k0"

    def test_top_k_tie_breaking(self):
        """Ties in count are broken alphabetically."""
        ss = SpaceSaving(k=5)
        ss.add("banana", count=5)
        ss.add("apple", count=5)
        ss.add("cherry", count=5)
        top = ss.top_k()
        keys = [k for k, _ in top]
        assert keys == ["apple", "banana", "cherry"]


# ── Weighted adds ───────────────────────────────────────────────────

class TestWeightedAdds:
    """Space-Saving with count > 1 per add."""

    def test_weighted_add(self):
        ss = SpaceSaving(k=5)
        ss.add("heavy", count=100)
        ss.add("light", count=1)
        assert ss.query("heavy") == 100
        assert ss.query("light") == 1
        assert ss.total == 101

    def test_weighted_eviction(self):
        """Weighted add on a new key at capacity: inherits min + count."""
        ss = SpaceSaving(k=2)
        ss.add("a", count=5)
        ss.add("b", count=1)
        # Full: a=5, b=1. Adding c with count=3 evicts b(1), c=1+3=4.
        ss.add("c", count=3)
        assert "b" not in ss.counters
        assert ss.counters["c"] == 4


# ── Edge cases ──────────────────────────────────────────────────────

class TestEdgeCases:
    """Boundary conditions and error handling."""

    def test_k_equals_one(self):
        """k=1 tracks exactly one key; the guarantee says any key with
        true count > N/1 = N must be present — which is vacuously true
        (no single key can have count > total). We just verify mechanics:
        one slot, eviction works, counter never exceeds total."""
        ss = SpaceSaving(k=1)
        ss.add("a")
        assert ss.query("a") == 1
        ss.add("b")  # evicts a (min=1), b = 1+1 = 2
        assert "a" not in ss.counters
        assert ss.query("b") == 2
        assert ss.total == 2
        assert len(ss.counters) == 1

    def test_zero_count_add(self):
        """Adding with count=0 is a no-op (updates total but not counters)."""
        ss = SpaceSaving(k=5)
        ss.add("a", count=0)
        assert ss.total == 0  # count=0 still adds to total
        assert "a" not in ss.counters

    def test_negative_count_rejected(self):
        ss = SpaceSaving(k=5)
        with pytest.raises(ValueError, match="negative"):
            ss.add("a", count=-1)

    def test_invalid_k(self):
        with pytest.raises(ValueError, match="k must be >= 1"):
            SpaceSaving(k=0)

    def test_at_capacity_no_overflow(self):
        """After many adds, monitored set never exceeds k."""
        ss = SpaceSaving(k=5)
        for i in range(1000):
            ss.add(f"key_{i}")
        assert len(ss.counters) <= 5
