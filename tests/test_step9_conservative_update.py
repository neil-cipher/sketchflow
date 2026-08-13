"""Step 9 — Conservative-Update CMS tests.

Gate: CU estimate <= plain-CMS estimate for every item on the same
stream, AND CU still never undercounts (estimate >= true count).

Additional checks:
- CU inherits query/row_values/inner_product/memory/serialization.
- CU reduces total counter inflation vs plain CMS.
- Weighted adds work correctly.
- Negative counts rejected.
"""

import collections

import pytest

from sketchflow.cms import CountMinSketch, size_cms
from sketchflow.cu_cms import ConservativeUpdateCMS
from sketchflow.streams import zipfian_stream


# ── 1. Core gate: CU <= plain CMS AND never undercounts ──────────


def test_cu_leq_plain_cms_and_never_undercounts():
    """For every key on a 10k Zipfian stream, CU estimate <= plain CMS
    estimate AND CU estimate >= true count."""
    seed = 42
    w, d = size_cms(0.01, 0.05)
    cms = CountMinSketch(width=w, depth=d, seed=seed)
    cu = ConservativeUpdateCMS(width=w, depth=d, seed=seed)
    exact = collections.Counter()

    stream = zipfian_stream(n_items=10_000, alpha=1.1, seed=99)
    for key in stream:
        cms.add(key)
        cu.add(key)
        exact[key] += 1

    for key, true_count in exact.items():
        cu_est = cu.query(key)
        cms_est = cms.query(key)
        assert cu_est <= cms_est, (
            f"CU ({cu_est}) > plain CMS ({cms_est}) for key {key!r}"
        )
        assert cu_est >= true_count, (
            f"CU undercount: {cu_est} < true {true_count} for key {key!r}"
        )


def test_cu_never_undercounts_many_seeds():
    """Never-undercount invariant across 50 seeds on a narrow sketch
    (width 64, depth 4) — heavy collisions stress the invariant."""
    for seed in range(50):
        cu = ConservativeUpdateCMS(width=64, depth=4, seed=seed)
        exact = collections.Counter()
        for key in zipfian_stream(n_items=2000, alpha=1.2, seed=seed + 1000):
            cu.add(key)
            exact[key] += 1
        for key, true_count in exact.items():
            assert cu.query(key) >= true_count


# ── 2. CU strictly reduces overestimation ────────────────────────


def test_cu_less_total_overestimation():
    """Summed overestimation across all keys is strictly less for CU
    than for plain CMS on a skewed stream."""
    seed = 7
    w, d = size_cms(0.01, 0.05)
    cms = CountMinSketch(width=w, depth=d, seed=seed)
    cu = ConservativeUpdateCMS(width=w, depth=d, seed=seed)
    exact = collections.Counter()

    for key in zipfian_stream(n_items=10_000, alpha=1.1, seed=42):
        cms.add(key)
        cu.add(key)
        exact[key] += 1

    cms_over = sum(cms.query(k) - v for k, v in exact.items())
    cu_over = sum(cu.query(k) - v for k, v in exact.items())
    assert cu_over < cms_over, (
        f"CU total overestimation ({cu_over}) not less than CMS ({cms_over})"
    )
    # CU overestimation should be meaningfully smaller, not just 1 less.
    assert cu_over < cms_over * 0.8, (
        f"CU overestimation ({cu_over}) not meaningfully less than CMS "
        f"({cms_over}); reduction only {1 - cu_over / cms_over:.1%}"
    )


# ── 3. Weighted add works ────────────────────────────────────────


def test_cu_weighted_add():
    """Conservative update with count > 1 still never undercounts and
    stays <= plain CMS."""
    seed = 55
    cms = CountMinSketch(width=256, depth=5, seed=seed)
    cu = ConservativeUpdateCMS(width=256, depth=5, seed=seed)
    exact = collections.Counter()

    items = [("alpha", 10), ("beta", 3), ("gamma", 100), ("delta", 1)]
    for key, count in items:
        cms.add(key, count)
        cu.add(key, count)
        exact[key] += count

    for key, true_count in exact.items():
        assert cu.query(key) >= true_count
        assert cu.query(key) <= cms.query(key)


def test_cu_rejects_negative_count():
    """Negative counts are rejected, same as plain CMS."""
    cu = ConservativeUpdateCMS(width=32, depth=2, seed=0)
    with pytest.raises(ValueError, match="negative"):
        cu.add("x", -1)


# ── 4. Totals agree ─────────────────────────────────────────────


def test_cu_total_matches_cms():
    """Both variants track the same stream length (total)."""
    seed = 42
    cms = CountMinSketch(width=128, depth=4, seed=seed)
    cu = ConservativeUpdateCMS(width=128, depth=4, seed=seed)
    for key in zipfian_stream(n_items=5000, alpha=1.0, seed=11):
        cms.add(key)
        cu.add(key)
    assert cu.total == cms.total == 5000


# ── 5. Inherited behaviour works ────────────────────────────────


def test_cu_row_values():
    """row_values works and each value >= true count."""
    cu = ConservativeUpdateCMS(width=128, depth=4, seed=0)
    exact = collections.Counter()
    for key in zipfian_stream(n_items=3000, alpha=1.1, seed=0):
        cu.add(key)
        exact[key] += 1

    for key, true_count in exact.items():
        vals = cu.row_values(key)
        assert len(vals) == 4
        assert all(v >= true_count for v in vals)


def test_cu_inner_product():
    """inner_product works between two CU sketches."""
    cu_a = ConservativeUpdateCMS(width=256, depth=4, seed=42)
    cu_b = ConservativeUpdateCMS(width=256, depth=4, seed=42)

    for key in zipfian_stream(n_items=3000, alpha=1.1, seed=10):
        cu_a.add(key)
    for key in zipfian_stream(n_items=3000, alpha=1.1, seed=20):
        cu_b.add(key)

    est = cu_a.inner_product(cu_b)
    # Inner product must be non-negative.
    assert est >= 0


def test_cu_serialize_round_trip():
    """to_bytes / from_bytes round-trip preserves CU sketch state."""
    cu = ConservativeUpdateCMS(width=128, depth=4, seed=77)
    for key in zipfian_stream(n_items=2000, alpha=1.0, seed=33):
        cu.add(key)

    blob = cu.to_bytes()
    restored = ConservativeUpdateCMS.from_bytes(blob)
    assert isinstance(restored, ConservativeUpdateCMS)
    assert restored.width == cu.width
    assert restored.depth == cu.depth
    assert restored.seed == cu.seed
    assert restored.total == cu.total

    # Every query must match.
    for key in ["0", "1", "10", "50", "99"]:
        assert restored.query(key) == cu.query(key)


def test_cu_bytes_used():
    """bytes_used returns a positive integer (inherited method works)."""
    cu = ConservativeUpdateCMS(width=64, depth=3, seed=0)
    cu.add("test")
    assert cu.bytes_used() > 0


# ── 6. Edge cases ───────────────────────────────────────────────


def test_cu_single_key_exact():
    """A single key inserted N times has estimate == N (no collisions
    possible with only one key)."""
    cu = ConservativeUpdateCMS(width=128, depth=4, seed=0)
    for _ in range(500):
        cu.add("only")
    assert cu.query("only") == 500


def test_cu_empty_query():
    """Querying a key never added returns 0 on a fresh sketch."""
    cu = ConservativeUpdateCMS(width=128, depth=4, seed=0)
    assert cu.query("missing") == 0
