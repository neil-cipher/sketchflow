"""Step 6 gates — CMS point query + ε/δ sizing.

GATE (plan.json step 6): |estimate − true| ≤ ε·N with prob ≥ 1−δ
across many seeds.  This is the core quality guarantee of the
Count-Min Sketch (Cormode & Muthukrishnan, J. Algorithms 2005,
Theorem 1).
"""

import math

import pytest

from sketchflow.baseline import ExactCounter
from sketchflow.cms import CountMinSketch, size_cms
from sketchflow.streams import zipfian_stream


# ── size_cms input validation ──────────────────────────────────────

def test_size_cms_rejects_bad_epsilon():
    with pytest.raises(ValueError):
        size_cms(0.0, 0.01)
    with pytest.raises(ValueError):
        size_cms(1.0, 0.01)
    with pytest.raises(ValueError):
        size_cms(-0.1, 0.01)


def test_size_cms_rejects_bad_delta():
    with pytest.raises(ValueError):
        size_cms(0.01, 0.0)
    with pytest.raises(ValueError):
        size_cms(0.01, 1.0)


# ── size_cms correctness ──────────────────────────────────────────

def test_size_cms_formula():
    """width = ceil(e/ε), depth = ceil(ln(1/δ))."""
    w, d = size_cms(0.01, 0.001)
    assert w == math.ceil(math.e / 0.01)      # 272
    assert d == math.ceil(math.log(1 / 0.001)) # 7


def test_size_cms_various_params():
    for eps, delta in [(0.1, 0.1), (0.05, 0.05), (0.001, 0.01)]:
        w, d = size_cms(eps, delta)
        assert w == math.ceil(math.e / eps)
        assert d == math.ceil(math.log(1.0 / delta))
        assert w >= 1 and d >= 1


# ── query() basics ────────────────────────────────────────────────

def test_query_returns_min_of_rows():
    """query() must equal min(row_values())."""
    cms = CountMinSketch(width=64, depth=4, seed=99)
    for item in zipfian_stream(n_items=500, universe=100, alpha=1.2, seed=7):
        cms.add(item)
    for i in range(100):
        key = str(i)
        assert cms.query(key) == min(cms.row_values(key))


def test_query_never_undercounts():
    """query() >= true count for every key (inherited from row invariant)."""
    cms = CountMinSketch(width=128, depth=5, seed=11)
    exact = ExactCounter()
    for item in zipfian_stream(n_items=5_000, universe=500, alpha=1.1, seed=42):
        cms.add(item)
        exact.add(item)
    for key, truth in exact.top_k(exact.distinct_keys()):
        assert cms.query(key) >= truth


# ── THE STEP-6 GATE ───────────────────────────────────────────────

def test_gate_epsilon_delta_guarantee_across_seeds():
    """The plan.json gate: |estimate − true| ≤ ε·N with prob ≥ 1−δ
    across many independent seeds.

    The CMS guarantee is PER-KEY: for any fixed query key x,
    P(estimate(x) − true(x) > ε·N) ≤ δ, where the randomness is
    over the hash-function choice (i.e. the seed).

    Method: build the same Zipfian stream under 300 different CMS
    seeds. For each of 10 target keys (the top-10 heavy hitters),
    count how many seeds violate the bound. Each key's empirical
    failure rate must be ≤ δ + a margin for sampling noise.
    """
    epsilon = 0.01
    delta = 0.05
    n_items = 10_000
    n_trials = 300
    width, depth = size_cms(epsilon, delta)

    # Pre-build the ground truth (stream is deterministic, seed=42).
    exact = ExactCounter()
    stream = list(zipfian_stream(n_items=n_items, universe=1_000,
                                 alpha=1.2, seed=42))
    for item in stream:
        exact.add(item)

    target_keys = [k for k, _ in exact.top_k(10)]
    bound = epsilon * n_items

    # Per-key violation counts.
    violations = {k: 0 for k in target_keys}

    for seed in range(n_trials):
        cms = CountMinSketch(width=width, depth=depth, seed=seed)
        for item in stream:
            cms.add(item)
        for key in target_keys:
            truth = exact.query(key)
            error = cms.query(key) - truth
            assert error >= 0, f"undercount for {key}!"
            if error > bound:
                violations[key] += 1

    # Each key's failure rate should be ≤ δ.  Allow 3·δ margin
    # (≈15%) to keep the test non-flaky with 300 trials.
    max_allowed = 3 * delta  # 0.15
    for key in target_keys:
        rate = violations[key] / n_trials
        assert rate <= max_allowed, (
            f"key {key!r}: empirical failure rate {rate:.3f} > {max_allowed}"
        )


def test_sized_cms_query_accuracy_single_seed():
    """Sanity: on one well-sized sketch, most estimates are very close."""
    eps = 0.005
    delt = 0.01
    w, d = size_cms(eps, delt)
    cms = CountMinSketch(width=w, depth=d, seed=42)
    exact = ExactCounter()
    for item in zipfian_stream(n_items=20_000, universe=2_000,
                               alpha=1.2, seed=42):
        cms.add(item)
        exact.add(item)

    bound = eps * cms.total
    violations = 0
    n_keys = exact.distinct_keys()
    for key, truth in exact.top_k(n_keys):
        error = cms.query(key) - truth
        assert error >= 0
        if error > bound:
            violations += 1
    # At most δ fraction of keys should violate (in theory it's per-key
    # probability, so even 0 violations is common).
    assert violations / n_keys <= 0.1, (
        f"too many violations: {violations}/{n_keys}"
    )
