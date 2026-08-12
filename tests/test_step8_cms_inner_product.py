"""Step 8 gates — CMS inner-product / join-size estimate.

GATE (plan.json step 8): estimated inner product within ε bound
of true dot product of frequency vectors.

The inner product of two frequency vectors f_a and f_b is:

    ⟨f_a, f_b⟩ = Σ_x  f_a(x) · f_b(x)

The CMS estimates this by taking the minimum across rows of the
row-wise dot product of the counter arrays (Cormode & Muthukrishnan,
J. Algorithms 2005, Section 3).  The error bound:

    estimate − true_inner_product ≤ ε · ‖a‖₁ · ‖b‖₁

with probability ≥ 1 − δ.
"""

import pytest

from sketchflow.baseline import ExactCounter
from sketchflow.cms import CountMinSketch, size_cms
from sketchflow.streams import zipfian_stream


# ── helpers ───────────────────────────────────────────────────────

def _true_inner_product(exact_a: ExactCounter, exact_b: ExactCounter) -> int:
    """Compute the exact inner product of two frequency vectors."""
    total = 0
    for key, count_a in exact_a.counts.items():
        count_b = exact_b.query(key)
        total += count_a * count_b
    return total


# ── input validation ─────────────────────────────────────────────

def test_inner_product_rejects_dimension_mismatch():
    """Sketches with different width or depth cannot be dot-producted."""
    a = CountMinSketch(width=64, depth=4, seed=0)
    b = CountMinSketch(width=128, depth=4, seed=0)
    with pytest.raises(ValueError, match="dimension mismatch"):
        a.inner_product(b)


def test_inner_product_rejects_depth_mismatch():
    a = CountMinSketch(width=64, depth=4, seed=0)
    b = CountMinSketch(width=64, depth=8, seed=0)
    with pytest.raises(ValueError, match="dimension mismatch"):
        a.inner_product(b)


def test_inner_product_rejects_seed_mismatch():
    """Same dimensions but different seeds -> different hash functions."""
    a = CountMinSketch(width=64, depth=4, seed=0)
    b = CountMinSketch(width=64, depth=4, seed=99)
    with pytest.raises(ValueError, match="seed mismatch"):
        a.inner_product(b)


# ── basic correctness ────────────────────────────────────────────

def test_inner_product_empty_sketches():
    """Two empty sketches have inner product 0."""
    a = CountMinSketch(width=64, depth=4, seed=42)
    b = CountMinSketch(width=64, depth=4, seed=42)
    assert a.inner_product(b) == 0


def test_inner_product_one_empty():
    """If one sketch is empty, inner product is 0."""
    a = CountMinSketch(width=64, depth=4, seed=42)
    b = CountMinSketch(width=64, depth=4, seed=42)
    for item in zipfian_stream(n_items=100, universe=20, alpha=1.0, seed=0):
        a.add(item)
    assert a.inner_product(b) == 0
    assert b.inner_product(a) == 0


def test_inner_product_never_undercounts():
    """Inner-product estimate >= true inner product (overestimate only)."""
    seed = 42
    a = CountMinSketch(width=128, depth=5, seed=seed)
    b = CountMinSketch(width=128, depth=5, seed=seed)
    exact_a = ExactCounter()
    exact_b = ExactCounter()

    for item in zipfian_stream(n_items=2_000, universe=200, alpha=1.2, seed=10):
        a.add(item)
        exact_a.add(item)
    for item in zipfian_stream(n_items=2_000, universe=200, alpha=1.2, seed=20):
        b.add(item)
        exact_b.add(item)

    true_ip = _true_inner_product(exact_a, exact_b)
    est_ip = a.inner_product(b)
    assert est_ip >= true_ip, (
        f"inner product undercount: {est_ip} < {true_ip}"
    )


def test_inner_product_is_symmetric():
    """a.inner_product(b) == b.inner_product(a)."""
    seed = 7
    a = CountMinSketch(width=64, depth=4, seed=seed)
    b = CountMinSketch(width=64, depth=4, seed=seed)
    for item in zipfian_stream(n_items=500, universe=50, alpha=1.0, seed=1):
        a.add(item)
    for item in zipfian_stream(n_items=500, universe=50, alpha=1.0, seed=2):
        b.add(item)
    assert a.inner_product(b) == b.inner_product(a)


def test_self_join_equals_l2_squared():
    """a.inner_product(a) == Σ f(x)², the squared L2 norm of the
    frequency vector.  On a collision-free sketch, this is exact."""
    # Use large width + few items to minimise collisions.
    cms = CountMinSketch(width=4096, depth=4, seed=42)
    exact = ExactCounter()
    for item in zipfian_stream(n_items=200, universe=50, alpha=1.0, seed=0):
        cms.add(item)
        exact.add(item)

    true_l2_sq = sum(c * c for c in exact.counts.values())
    est_l2_sq = cms.inner_product(cms)
    # With 200 items in width-4096, collisions are rare — estimate
    # should be very close.
    assert est_l2_sq >= true_l2_sq
    # Allow at most 5% relative overshoot.
    assert est_l2_sq <= true_l2_sq * 1.05, (
        f"self-join too high: {est_l2_sq} vs true {true_l2_sq}"
    )


def test_inner_product_disjoint_universes():
    """If two streams share no keys, true inner product is 0.
    The CMS estimate may be > 0 due to hash collisions but should
    still be small relative to the product of stream lengths."""
    seed = 42
    w, d = size_cms(0.01, 0.05)
    a = CountMinSketch(width=w, depth=d, seed=seed)
    b = CountMinSketch(width=w, depth=d, seed=seed)

    # Stream a: keys "a0"..."a99"; stream b: keys "b0"..."b99"
    for i in range(1000):
        a.add(f"a{i % 100}")
    for i in range(1000):
        b.add(f"b{i % 100}")

    est = a.inner_product(b)
    # True inner product is 0; estimate should be bounded by ε·N_a·N_b.
    bound = 0.01 * a.total * b.total
    assert est >= 0
    assert est <= bound, (
        f"disjoint estimate {est} exceeds bound {bound}"
    )


# ── THE STEP-8 GATE ──────────────────────────────────────────────

def test_gate_inner_product_within_epsilon_bound():
    """Plan.json gate: estimated inner product within ε bound of
    true dot product of frequency vectors.

    Error bound (Cormode & Muthukrishnan 2005): for properly-sized
    sketches with width = ⌈e/ε⌉ and depth = ⌈ln(1/δ)⌉:

        estimate − true ≤ ε · ‖a‖₁ · ‖b‖₁

    with probability ≥ 1−δ over hash randomness.

    Method: 200 trials with different seeds. Two independent Zipfian
    streams per trial. Measure violation rate (per-trial, not per-key).
    """
    epsilon = 0.01
    delta = 0.05
    n_items = 5_000
    n_trials = 200
    width, depth = size_cms(epsilon, delta)

    # Fixed streams (deterministic) — only hash seeds vary.
    stream_a = list(zipfian_stream(n_items=n_items, universe=500,
                                   alpha=1.2, seed=42))
    stream_b = list(zipfian_stream(n_items=n_items, universe=500,
                                   alpha=1.1, seed=99))

    exact_a = ExactCounter()
    exact_b = ExactCounter()
    for item in stream_a:
        exact_a.add(item)
    for item in stream_b:
        exact_b.add(item)
    true_ip = _true_inner_product(exact_a, exact_b)

    violations = 0
    for seed in range(n_trials):
        a = CountMinSketch(width=width, depth=depth, seed=seed)
        b = CountMinSketch(width=width, depth=depth, seed=seed)
        for item in stream_a:
            a.add(item)
        for item in stream_b:
            b.add(item)

        est = a.inner_product(b)
        assert est >= true_ip, (
            f"seed {seed}: undercount {est} < {true_ip}"
        )
        error = est - true_ip
        bound = epsilon * a.total * b.total
        if error > bound:
            violations += 1

    # Empirical violation rate should be ≤ δ.
    # Allow 3·δ margin to keep the test non-flaky.
    rate = violations / n_trials
    assert rate <= 3 * delta, (
        f"inner-product violation rate {rate:.3f} > {3 * delta} "
        f"({violations}/{n_trials} trials)"
    )


def test_inner_product_weighted_add():
    """inner_product works correctly with weighted adds (count > 1)."""
    seed = 42
    a = CountMinSketch(width=256, depth=5, seed=seed)
    b = CountMinSketch(width=256, depth=5, seed=seed)
    exact_a = ExactCounter()
    exact_b = ExactCounter()

    # Weighted adds
    for i in range(50):
        key = str(i)
        w_a = (i + 1) * 3
        w_b = (50 - i) * 2
        a.add(key, w_a)
        b.add(key, w_b)
        exact_a.add(key, w_a)
        exact_b.add(key, w_b)

    true_ip = _true_inner_product(exact_a, exact_b)
    est_ip = a.inner_product(b)
    assert est_ip >= true_ip
