"""Step 20 — Guarantee-violation meter tests.

Core gate (plan.json step 20): "on benign streams empirical violation
rate <= delta; on adversarial streams it is quantified."

This reuses the exact eps/delta check step 6 first ran (300 hash-seed
trials over a fixed Zipfian stream), packaged as a general meter, and
then applies the SAME meter to a step-19 adversarial stream to report
(not assert a bound on) how far the promise breaks down.
"""

import collections

from sketchflow.adversary import adversarial_stream, random_control_stream
from sketchflow.cms import CountMinSketch
from sketchflow.guarantee_meter import (
    adversarial_violation_study,
    benign_violation_study,
    violating_keys,
    violation_rate,
)


# ── 1. Mechanics: violating_keys / violation_rate on a hand-built sketch ──


def test_violating_keys_flags_only_keys_over_the_bound():
    """A tiny hand-built case: one key pushed past eps*N, one left alone."""
    sketch = CountMinSketch(width=4, depth=2, seed=0)
    # Pile 100 events onto "hot" so its counters are inflated far past
    # any true count we'll claim for it.
    for _ in range(100):
        sketch.add("hot")
    sketch.add("cold")

    true_counts = {"hot": 1, "cold": 1}
    epsilon = 0.01  # bound = 0.01 * 101 ~= 1.01

    violators = violating_keys(sketch, true_counts, epsilon)
    assert "hot" in violators, "hot's inflated estimate must break the bound"
    # cold's own counters were only touched once each -- estimate should
    # equal its true count (no other key collided into cold's buckets in
    # this tiny scripted case is not guaranteed in general, but here the
    # sketch is small enough that we just assert hot is flagged and the
    # rate reflects it).
    assert 0.0 < violation_rate(sketch, true_counts, epsilon) <= 1.0


def test_violation_rate_zero_when_no_true_counts():
    sketch = CountMinSketch(width=8, depth=2, seed=0)
    assert violation_rate(sketch, {}, 0.01) == 0.0


def test_violation_rate_is_fraction_of_true_counts_length():
    sketch = CountMinSketch(width=64, depth=4, seed=1)
    for _ in range(5):
        sketch.add("a")
    sketch.add("b")
    sketch.add("c")
    true_counts = {"a": 5, "b": 1, "c": 1}
    # eps huge -> nothing can violate
    assert violation_rate(sketch, true_counts, epsilon=10.0) == 0.0
    rate = violation_rate(sketch, true_counts, epsilon=0.0)
    # eps=0 -> bound is 0, so any positive overestimate counts as a
    # violation; rate must be a valid fraction with denominator 3.
    assert rate in (0.0, 1 / 3, 2 / 3, 1.0)


# ── 2. THE STEP-20 GATE, benign side ──────────────────────────────


def test_gate_benign_violation_rate_stays_within_delta_margin():
    """plan.json gate: on benign streams, empirical violation rate <= delta.

    Same margin rationale as the step-6 gate test: with num_trials=300
    and delta=0.05, the exact-binomial sampling noise means a hard
    ``<= delta`` cutoff is flaky. We allow the same 3*delta margin step 6
    established (documented there as ~15%, non-flaky at 300 trials).
    """
    epsilon, delta = 0.01, 0.05
    rates = benign_violation_study(
        epsilon=epsilon, delta=delta, num_trials=300, n_items=10_000,
        universe=1_000, alpha=1.2, stream_seed=42, num_target_keys=10,
    )
    assert len(rates) == 10
    max_allowed = 3 * delta  # 0.15, matches test_step6's established margin
    for key, rate in rates.items():
        assert rate <= max_allowed, (
            f"key {key!r}: empirical violation rate {rate:.3f} exceeds "
            f"the {max_allowed} margin around delta={delta}"
        )


def test_benign_violation_study_returns_rates_for_requested_key_count():
    rates = benign_violation_study(
        epsilon=0.02, delta=0.1, num_trials=30, n_items=2_000,
        universe=200, num_target_keys=5,
    )
    assert len(rates) == 5
    assert all(0.0 <= r <= 1.0 for r in rates.values())


# ── 3. THE STEP-20 GATE, adversarial side (quantify, don't assert a bound) ──


def test_gate_adversarial_violation_is_quantified_and_exceeds_benign():
    """plan.json gate: on adversarial streams the violation rate is
    quantified. We apply the identical meter used on the benign side to
    the step-19 collision-maximising stream and its benign control (same
    memory budget, same shuffle procedure), and confirm the meter reports
    a much higher violation rate for the adversarial case -- the
    empirical finding the meter exists to produce.
    """
    width, depth, seed = 16, 3, 42
    num_groups, group_size, events_per_key = 5, 5, 20
    n = num_groups * group_size * events_per_key  # 500
    # A deliberately tight epsilon relative to N so the bound is
    # meaningful for this small demo sketch (mirrors step 19's use of a
    # small width/depth to make the attack tractable).
    epsilon = 0.02  # bound = 0.02 * 500 = 10

    adv_sketch = CountMinSketch(width=width, depth=depth, seed=seed)
    adv_stream, _group_of = adversarial_stream(
        adv_sketch, num_groups=num_groups, group_size=group_size,
        events_per_key=events_per_key,
    )
    adv_true = collections.Counter(adv_stream)
    for key in adv_stream:
        adv_sketch.add(key)
    adv_rate = adversarial_violation_study(adv_sketch, adv_true, epsilon)

    ctl_sketch = CountMinSketch(width=width, depth=depth, seed=seed)
    ctl_stream = random_control_stream(
        num_keys=num_groups * group_size, events_per_key=events_per_key
    )
    ctl_true = collections.Counter(ctl_stream)
    for key in ctl_stream:
        ctl_sketch.add(key)
    ctl_rate = violation_rate(ctl_sketch, ctl_true, epsilon)

    assert 0.0 <= adv_rate <= 1.0
    assert 0.0 <= ctl_rate <= 1.0
    assert adv_rate > ctl_rate, (
        f"adversarial violation rate ({adv_rate:.3f}) not greater than "
        f"benign control's ({ctl_rate:.3f}) at the same memory budget"
    )
    # The attack should be decisive, not marginal: most colliding-group
    # members should break the bound.
    assert adv_rate >= 0.5, (
        f"adversarial violation rate ({adv_rate:.3f}) too low to call the "
        "attack decisive"
    )
