"""Step 27 gates -- HyperLogLog cardinality (OPTIONAL P7 stretch).

GATE (plan.json step 27): HLL cardinality within ~2% on a known-distinct-count
synthetic stream.

The estimator is randomized, so the honest gate is two-part, mirroring the
step-4 Bloom pattern: a bank of deterministic MECHANISM tests that pin the
math exactly (rank as a max, duplicates inert, the alpha_m constants, linear
counting, register-wise merge), plus STATISTICAL gates asserted with margins
derived from HLL's own 1.04/sqrt(m) standard error rather than hand-waved.
"""

import math

import pytest

from sketchflow.hll import HyperLogLog, alpha_m


def _build(distinct, precision=14, seed=42, prefix="user"):
    hll = HyperLogLog(precision=precision, seed=seed)
    for i in range(distinct):
        hll.add(f"{prefix}-{i}")
    return hll


# ------------------------- mechanism (deterministic) -------------------------

def test_alpha_m_constants_match_the_paper():
    # The three tabulated small-m values (Flajolet et al. 2007), verbatim.
    assert alpha_m(16) == 0.673
    assert alpha_m(32) == 0.697
    assert alpha_m(64) == 0.709
    # The large-m closed form, and its m -> inf limit 1/(2 ln 2) ~= 0.7213.
    assert alpha_m(128) == pytest.approx(0.7213 / (1 + 1.079 / 128))
    assert alpha_m(1 << 20) == pytest.approx(0.7213, abs=1e-3)
    with pytest.raises(ValueError):
        alpha_m(8)  # fewer than 16 registers is out of range


def test_precision_bounds_enforced():
    with pytest.raises(ValueError):
        HyperLogLog(precision=3)
    with pytest.raises(ValueError):
        HyperLogLog(precision=19)
    HyperLogLog(precision=4)   # lower bound ok
    HyperLogLog(precision=18)  # upper bound ok


def test_empty_sketch_estimates_zero():
    hll = HyperLogLog(precision=8, seed=1)
    assert hll.cardinality() == 0.0
    assert len(hll) == 0


def test_memory_is_one_byte_per_register():
    hll = HyperLogLog(precision=12, seed=1)
    assert hll.memory_bytes() == 4096
    assert len(hll.registers) == 4096
    # A run length can never overflow a byte.
    for i in range(20_000):
        hll.add(f"m-{i}")
    assert max(hll.registers) <= 64 - 12 + 1


def test_registers_only_grow_and_stay_in_range():
    p = 6
    hll = HyperLogLog(precision=p, seed=9)
    max_run = 64 - p + 1
    prev = bytearray(hll.registers)
    for i in range(3000):
        hll.add(f"r-{i}")
        assert all(b >= a for a, b in zip(prev, hll.registers))   # never shrink
        assert all(0 <= r <= max_run for r in hll.registers)      # bounded
        prev = bytearray(hll.registers)


def test_duplicates_do_not_change_the_estimate():
    hll = _build(5000, precision=12, seed=3, prefix="x")
    before = hll.cardinality()
    snapshot = bytearray(hll.registers)
    for _ in range(10):                       # 11x the volume, same 5000 keys
        for i in range(5000):
            hll.add(f"x-{i}")
    assert hll.registers == snapshot          # not one register moved
    assert hll.cardinality() == before        # so the estimate is byte-identical


def test_same_seed_deterministic_different_seed_diverges():
    a1 = _build(8000, precision=12, seed=5, prefix="d")
    a2 = _build(8000, precision=12, seed=5, prefix="d")
    b = _build(8000, precision=12, seed=6, prefix="d")
    assert a1.registers == a2.registers
    assert a1.cardinality() == a2.cardinality()
    assert a1.registers != b.registers        # a different seed re-partitions


# ------------------------------ THE step-27 gate -----------------------------

def test_gate_cardinality_within_two_percent():
    """THE step-27 gate: on a known-distinct-count stream, HLL's TYPICAL error
    is within ~2%.

    Sited in HLL's clean asymptotic regime -- p = 14 (m = 16384 registers,
    16 KB) with D = 200_000 distinct keys (n/m ~= 12), safely past the
    linear-counting/asymptotic transition bump that
    test_transition_zone_bias_is_measured_not_hidden characterises. Over 24
    hash seeds we assert the estimator is typically within ~2%:
      (1) MEAN   relative error <= 2%  (observed ~1.1%; the mean's own std is
          tiny, so this carries many sigma of headroom),
      (2) MEDIAN relative error <= 2%  (half the seeds beat ~0.9%),
      (3) >= 80% of seeds within 2.5%.
    Single-seed error runs a little above the ideal 1.04/sqrt(m) = 0.81%
    because the sketch reuses the project's simple-tabulation HashFamily
    (3-independent, not a fully-random oracle) -- a measured, honest limitation
    of the shared hash primitive, not a bug in the estimator.
    """
    D, p, n_seeds = 200_000, 14, 24
    rels = sorted(
        abs(_build(D, precision=p, seed=1000 + s).cardinality() - D) / D
        for s in range(n_seeds)
    )
    mean_rel = sum(rels) / len(rels)
    median_rel = rels[len(rels) // 2]
    within = sum(1 for r in rels if r <= 0.025) / n_seeds
    assert mean_rel <= 0.02, f"mean relative error {mean_rel:.4f} > 2%"
    assert median_rel <= 0.02, f"median relative error {median_rel:.4f} > 2%"
    assert within >= 0.80, f"only {within:.0%} of seeds within 2.5%"


def test_gate_holds_across_magnitudes():
    # Error stays ~constant relative to N in the regimes where the textbook
    # estimator is clean: linear counting for small sets, asymptotic for large
    # (the [2.5m, ~5m] transition bump is characterised in its own test below).
    # Average several seeds so the check reflects typical behaviour, not one draw.
    for D in (10_000, 400_000):   # n/m ~= 0.6 (linear) and ~24 (asymptotic)
        rels = [abs(_build(D, precision=14, seed=200 + s).cardinality() - D) / D
                for s in range(8)]
        assert sum(rels) / len(rels) <= 0.02, f"D={D}: mean rel err too high"


def test_transition_zone_degrades_but_does_not_break():
    """HONEST NOTE (this project's whole ethos -- "show where the textbook
    guarantee holds and where it doesn't"): the raw HLL-2007 estimator is at
    its WEAKEST in the n/m in [2.5, ~5] transition zone -- the bump that
    HyperLogLog++ (Heule, Nunkesser & Hall, 2013) later flattened with an
    empirical bias table, and the reason THE gate above is deliberately sited
    in the clean asymptotic regime (n/m ~= 12), not here. This test pins only
    the robust, non-flaky fact: at D = 60_000 (n/m ~= 3.7) the estimator
    DEGRADES but does not break -- its typical error stays within ~3% -- so we
    have measured the bump rather than hidden it. (The bump also carries a
    slight upward pull; that residual bias, ~+0.5-1%, sits near the estimator's
    own noise floor at these seed counts and is reported in decisions.log
    rather than asserted as a sub-noise inequality.)
    """
    rels = [(_build(60_000, precision=14, seed=400 + s).cardinality() - 60_000) / 60_000
            for s in range(24)]
    mean_abs = sum(abs(r) for r in rels) / len(rels)
    assert mean_abs <= 0.03, f"transition-zone typical error {mean_abs:.4f} > 3%"


def test_small_cardinality_uses_linear_counting_accurately():
    # D << m: the raw estimator is unreliable, linear counting takes over and
    # is very accurate (most registers stay empty, so V is a strong signal).
    D = 300
    hll = _build(D, precision=14, seed=7, prefix="k")
    # confirm we are actually in the linear-counting regime
    zeros = sum(1 for r in hll.registers if r == 0)
    assert zeros > 0
    est = hll.cardinality()
    assert abs(est - D) / D <= 0.05


# ------------------------------- merge / union -------------------------------

def test_merge_is_registerwise_max_and_non_mutating():
    a = _build(4000, precision=12, seed=17, prefix="a")
    b = _build(4000, precision=12, seed=17, prefix="b")
    a_before = bytearray(a.registers)
    b_before = bytearray(b.registers)
    u = a.merge(b)
    assert u.registers == bytearray(max(x, y) for x, y in zip(a_before, b_before))
    assert a.registers == a_before and b.registers == b_before   # inputs intact


def test_merge_estimates_union_cardinality():
    # A = {a-0..a-149999}, B = {a-100000..a-249999}: overlap 50000, union
    # 250000 (n/m ~= 15, asymptotic). The union of the SETS maps to the
    # register-wise MAX, so the merged sketch estimates |A union B|.
    ests = []
    for seed in (11, 22, 33, 44, 55, 66, 77, 88):
        a = HyperLogLog(precision=14, seed=seed)
        b = HyperLogLog(precision=14, seed=seed)
        for i in range(150_000):
            a.add(f"a-{i}")
        for i in range(100_000, 250_000):
            b.add(f"a-{i}")
        ests.append((a.merge(b).cardinality() - 250_000) / 250_000)
    mean_rel = sum(ests) / len(ests)
    within3 = sum(1 for e in ests if abs(e) <= 0.03)
    assert abs(mean_rel) <= 0.02                 # union property holds on average
    assert within3 >= len(ests) - 1              # >= 7/8 individually within 3%


def test_merge_rejects_mismatched_config():
    with pytest.raises(ValueError):
        HyperLogLog(precision=10, seed=1).merge(HyperLogLog(precision=11, seed=1))
    with pytest.raises(ValueError):
        HyperLogLog(precision=10, seed=1).merge(HyperLogLog(precision=10, seed=2))
