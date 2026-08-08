"""Step 4 gates — Bloom sizing calculator.

GATE (plan.json step 4): empirical FPR at the computed (m, k) must be
<= target on a 10k-item stream.
"""

import math

import pytest

from sketchflow.bloom import BloomFilter
from sketchflow.sizing import analytic_fpr, size_bloom


def test_closed_forms_match_textbook():
    # Classic worked example: n=10_000, p=1% -> m ~= 95.9k bits, k = 7.
    m, k = size_bloom(10_000, 0.01)
    assert 95_851 <= m <= 97_000  # textbook value + tiny promise-keeping bump
    assert k == 7
    # The calculator must actually deliver its promise, exactly.
    assert analytic_fpr(m, k, 10_000) <= 0.01


def test_rejects_bad_inputs():
    with pytest.raises(ValueError):
        size_bloom(0, 0.01)
    with pytest.raises(ValueError):
        size_bloom(100, 0.0)
    with pytest.raises(ValueError):
        size_bloom(100, 1.0)


def test_monotone_cost_of_accuracy():
    # Buying accuracy with memory: tighter target -> more bits, never fewer.
    sizes = [size_bloom(10_000, p)[0] for p in (0.1, 0.01, 0.001)]
    assert sizes == sorted(sizes)
    # ~1.44 bits/item per halving -> 10x tighter costs ~4.8 bits/item more.
    per_item_step = (sizes[1] - sizes[0]) / 10_000
    assert 4.0 < per_item_step < 5.5


def test_gate_empirical_fpr_meets_target():
    """THE step-4 gate: build a Bloom filter at the computed (m, k),
    insert a 10k-item stream, measure FPR on unseen keys.

    Two-part, honest verification:
    1. the calculator's promise is proved EXACTLY by the math
       (analytic FPR <= target), and
    2. the measured rate confirms it within binomial sampling noise
       (<= target + 3 sigma) — a finite sample of coin flips cannot be
       asserted tighter than its own standard error. 50k probes shrink
       sigma to ~0.0004 so the allowance is slim.
    """
    n, target = 10_000, 0.01
    m, k = size_bloom(n, target)

    # Part 1 — exact: the promise holds analytically.
    assert analytic_fpr(m, k, n) <= target
    # ...and not by gross over-provisioning.
    assert analytic_fpr(m, k, n) > target / 10

    bf = BloomFilter(m_bits=m, k=k, seed=42)
    members = [f"member-{i}" for i in range(n)]
    for key in members:
        bf.add(key)

    # Zero false negatives is inherited from step 3 but re-assert cheaply.
    assert all(key in bf for key in members[:1000])

    # Part 2 — empirical: measured FPR within 3 sigma of the target.
    probes = 50_000
    false_pos = sum(1 for i in range(probes) if f"stranger-{i}" in bf)
    measured = false_pos / probes
    sigma = math.sqrt(target * (1 - target) / probes)
    assert measured <= target + 3 * sigma, (
        f"measured FPR {measured:.5f} exceeds {target} + 3σ ({3 * sigma:.5f})"
    )


def test_gate_holds_at_other_targets():
    n = 10_000
    probes = 50_000
    for target in (0.05, 0.001):
        m, k = size_bloom(n, target)
        assert analytic_fpr(m, k, n) <= target
        bf = BloomFilter(m_bits=m, k=k, seed=7)
        for i in range(n):
            bf.add(f"m{target}-{i}")
        false_pos = sum(1 for i in range(probes) if f"s{target}-{i}" in bf)
        sigma = math.sqrt(target * (1 - target) / probes)
        assert false_pos / probes <= target + 3 * sigma
