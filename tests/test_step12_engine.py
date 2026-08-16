"""Step 12 gate tests: CMS + Space-Saving combined engine.

Gate from plan.json:
    "test: end-to-end on synthetic stream returns correct heavy hitters
     with CMS-estimated counts"

These tests verify:
1. End-to-end correctness: heavy hitters match exact baseline on Zipfian streams.
2. CMS estimates used (not raw Space-Saving counts) in heavy_hitters().
3. Conservative-update mode works end-to-end.
4. Engine totals stay in sync across CMS and Space-Saving.
5. Weighted adds work correctly.
6. Edge cases: single item, k=1, empty stream.
7. Summary dict is well-formed.
8. estimate() matches direct CMS query.
"""

import collections

from sketchflow.baseline import ExactCounter
from sketchflow.cms import CountMinSketch
from sketchflow.cu_cms import ConservativeUpdateCMS
from sketchflow.engine import SketchEngine
from sketchflow.streams import zipfian_stream


# ── 1. End-to-end: heavy hitters match exact top-k on Zipfian ────────

def test_engine_heavy_hitters_match_exact_top10():
    """On a 10k Zipfian stream with enough headroom (top_k=50),
    the engine's top-10 heavy hitters should be exactly the true top-10."""
    stream = list(zipfian_stream(n_items=10_000, alpha=1.2, universe=200, seed=42))
    exact = ExactCounter()
    for item in stream:
        exact.add(item)

    engine = SketchEngine(epsilon=0.01, delta=0.01, top_k=50, seed=99)
    for item in stream:
        engine.add(item)

    exact_top10_keys = {k for k, _ in exact.top_k(10)}
    engine_top10 = engine.heavy_hitters(n=10)
    engine_top10_keys = {k for k, _ in engine_top10}

    assert engine_top10_keys == exact_top10_keys, (
        f"engine top-10 {engine_top10_keys} != exact top-10 {exact_top10_keys}"
    )


def test_engine_heavy_hitters_across_seeds():
    """Across 10 seeds, engine top-10 always matches exact top-10
    (with sufficient k headroom)."""
    for seed in range(10):
        stream = list(zipfian_stream(n_items=10_000, alpha=1.2, universe=200, seed=seed))
        exact = ExactCounter()
        for item in stream:
            exact.add(item)

        engine = SketchEngine(epsilon=0.005, delta=0.01, top_k=50, seed=seed + 100)
        for item in stream:
            engine.add(item)

        exact_top10_keys = {k for k, _ in exact.top_k(10)}
        engine_top10_keys = {k for k, _ in engine.heavy_hitters(n=10)}

        assert engine_top10_keys == exact_top10_keys, (
            f"seed {seed}: engine top-10 mismatch"
        )


# ── 2. CMS estimates used, not Space-Saving counts ──────────────────

def test_heavy_hitters_use_cms_estimates():
    """The counts in heavy_hitters() should come from the CMS, not from
    Space-Saving's internal counters."""
    stream = list(zipfian_stream(n_items=5000, alpha=1.5, universe=100, seed=77))
    engine = SketchEngine(epsilon=0.01, delta=0.01, top_k=30, seed=77)
    for item in stream:
        engine.add(item)

    hh = engine.heavy_hitters()
    for key, count in hh:
        assert count == engine.cms.query(key), (
            f"heavy_hitters count for {key!r} ({count}) != "
            f"CMS query ({engine.cms.query(key)})"
        )


def test_cms_estimates_are_overestimates():
    """Every CMS estimate should be >= true count (never-undercount)."""
    stream = list(zipfian_stream(n_items=10_000, alpha=1.2, universe=200, seed=42))
    true_counts = collections.Counter(stream)

    engine = SketchEngine(epsilon=0.01, delta=0.01, top_k=50, seed=42)
    for item in stream:
        engine.add(item)

    for key, true_count in true_counts.items():
        est = engine.estimate(key)
        assert est >= true_count, (
            f"undercount for {key!r}: estimate {est} < true {true_count}"
        )


# ── 3. Conservative-update mode ─────────────────────────────────────

def test_conservative_mode_uses_cu_cms():
    """When conservative=True, the engine's CMS should be a ConservativeUpdateCMS."""
    engine = SketchEngine(epsilon=0.01, delta=0.01, top_k=10, conservative=True)
    assert isinstance(engine.cms, ConservativeUpdateCMS)


def test_conservative_mode_reduces_overestimation():
    """CU engine estimates should be <= plain engine estimates for every key."""
    stream = list(zipfian_stream(n_items=10_000, alpha=1.2, universe=200, seed=42))

    plain = SketchEngine(epsilon=0.01, delta=0.01, top_k=50, seed=42)
    cu = SketchEngine(epsilon=0.01, delta=0.01, top_k=50, seed=42, conservative=True)

    for item in stream:
        plain.add(item)
        cu.add(item)

    true_counts = collections.Counter(stream)
    total_overest_plain = 0
    total_overest_cu = 0
    for key in true_counts:
        plain_est = plain.estimate(key)
        cu_est = cu.estimate(key)
        assert cu_est <= plain_est, (
            f"CU overestimates more than plain for {key!r}: "
            f"CU={cu_est} > plain={plain_est}"
        )
        total_overest_plain += plain_est - true_counts[key]
        total_overest_cu += cu_est - true_counts[key]

    # CU total overestimation should be strictly less (by a meaningful margin)
    assert total_overest_cu < total_overest_plain, (
        f"CU total overestimation ({total_overest_cu}) not less than "
        f"plain ({total_overest_plain})"
    )


def test_conservative_heavy_hitters_correct():
    """CU engine heavy hitters should match exact top-10."""
    stream = list(zipfian_stream(n_items=10_000, alpha=1.2, universe=200, seed=55))
    exact = ExactCounter()
    for item in stream:
        exact.add(item)

    engine = SketchEngine(epsilon=0.005, delta=0.01, top_k=50, seed=55, conservative=True)
    for item in stream:
        engine.add(item)

    exact_top10_keys = {k for k, _ in exact.top_k(10)}
    engine_top10_keys = {k for k, _ in engine.heavy_hitters(n=10)}
    assert engine_top10_keys == exact_top10_keys


# ── 4. Totals in sync ───────────────────────────────────────────────

def test_totals_in_sync():
    """engine.total, CMS total, and Space-Saving total should all agree."""
    stream = list(zipfian_stream(n_items=5000, alpha=1.0, universe=100, seed=33))
    engine = SketchEngine(epsilon=0.01, delta=0.01, top_k=20, seed=33)
    for item in stream:
        engine.add(item)

    assert engine.total == len(stream)
    assert engine.cms.total == len(stream)
    assert engine.tracker.total == len(stream)


# ── 5. Weighted adds ────────────────────────────────────────────────

def test_weighted_adds():
    """Adding with count > 1 should be equivalent to repeated single adds."""
    engine_single = SketchEngine(epsilon=0.01, delta=0.01, top_k=10, seed=42)
    engine_bulk = SketchEngine(epsilon=0.01, delta=0.01, top_k=10, seed=42)

    items = [("alpha", 5), ("beta", 3), ("alpha", 2), ("gamma", 10)]
    for key, count in items:
        for _ in range(count):
            engine_single.add(key)
        engine_bulk.add(key, count=count)

    for key in ("alpha", "beta", "gamma"):
        assert engine_single.estimate(key) == engine_bulk.estimate(key), (
            f"weighted add mismatch for {key!r}"
        )
    assert engine_single.total == engine_bulk.total


# ── 6. Edge cases ───────────────────────────────────────────────────

def test_empty_stream():
    """An engine with no adds should return empty heavy hitters."""
    engine = SketchEngine(epsilon=0.01, delta=0.01, top_k=10)
    assert engine.heavy_hitters() == []
    assert engine.total == 0
    assert engine.estimate("anything") == 0


def test_single_item():
    """A single add should produce exactly one heavy hitter."""
    engine = SketchEngine(epsilon=0.01, delta=0.01, top_k=10, seed=42)
    engine.add("only_key")
    hh = engine.heavy_hitters()
    assert len(hh) == 1
    assert hh[0][0] == "only_key"
    assert hh[0][1] >= 1  # CMS estimate >= true count


def test_k_equals_1():
    """Engine with top_k=1 should track only the single heaviest hitter."""
    stream = list(zipfian_stream(n_items=5000, alpha=1.5, universe=100, seed=42))
    exact = ExactCounter()
    for item in stream:
        exact.add(item)

    engine = SketchEngine(epsilon=0.01, delta=0.01, top_k=1, seed=42)
    for item in stream:
        engine.add(item)

    exact_top1_key = exact.top_k(1)[0][0]
    engine_top1 = engine.heavy_hitters(n=1)
    assert len(engine_top1) == 1
    assert engine_top1[0][0] == exact_top1_key


# ── 7. Summary dict ─────────────────────────────────────────────────

def test_summary_well_formed():
    """summary() should return a dict with all expected keys."""
    engine = SketchEngine(epsilon=0.01, delta=0.05, top_k=10, seed=42)
    for item in ["a", "b", "a", "c", "a", "b"]:
        engine.add(item)

    s = engine.summary()
    assert s["epsilon"] == 0.01
    assert s["delta"] == 0.05
    assert s["top_k"] == 10
    assert s["conservative"] is False
    assert s["total"] == 6
    assert isinstance(s["cms_width"], int)
    assert isinstance(s["cms_depth"], int)
    assert isinstance(s["heavy_hitters"], list)
    # "a" should be the top hitter
    assert s["heavy_hitters"][0][0] == "a"


# ── 8. estimate() matches direct CMS query ──────────────────────────

def test_estimate_equals_cms_query():
    """engine.estimate(key) should be identical to engine.cms.query(key)."""
    stream = list(zipfian_stream(n_items=3000, alpha=1.0, universe=50, seed=42))
    engine = SketchEngine(epsilon=0.01, delta=0.01, top_k=20, seed=42)
    for item in stream:
        engine.add(item)

    for key in set(stream):
        assert engine.estimate(key) == engine.cms.query(key)


# ── 9. Plain mode uses plain CMS ────────────────────────────────────

def test_plain_mode_uses_plain_cms():
    """When conservative=False (default), the CMS should be a plain CountMinSketch."""
    engine = SketchEngine(epsilon=0.01, delta=0.01, top_k=10)
    assert isinstance(engine.cms, CountMinSketch)
    assert not isinstance(engine.cms, ConservativeUpdateCMS)


# ── 10. Validation: bad parameters ──────────────────────────────────

def test_invalid_top_k():
    """top_k < 1 should raise ValueError."""
    try:
        SketchEngine(epsilon=0.01, delta=0.01, top_k=0)
        assert False, "should have raised ValueError"
    except ValueError:
        pass


def test_invalid_epsilon():
    """epsilon outside (0,1) should raise ValueError (from size_cms)."""
    try:
        SketchEngine(epsilon=0.0, delta=0.01, top_k=10)
        assert False, "should have raised ValueError"
    except ValueError:
        pass


def test_invalid_delta():
    """delta outside (0,1) should raise ValueError (from size_cms)."""
    try:
        SketchEngine(epsilon=0.01, delta=1.0, top_k=10)
        assert False, "should have raised ValueError"
    except ValueError:
        pass
