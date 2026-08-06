"""Step 3 gates: ZERO false negatives ever; FPR within analytic tolerance."""
import math

from sketchflow.bloom import BloomFilter


def test_never_a_false_negative():
    bf = BloomFilter(m_bits=16_384, k=4, seed=7)
    keys = [f"flow-{i}" for i in range(5000)]
    for k in keys:
        bf.add(k)
    assert all(k in bf for k in keys)  # the one-sided promise, absolute


def test_false_positive_rate_near_analytic():
    m, k, n = 16_384, 4, 2000
    bf = BloomFilter(m_bits=m, k=k, seed=42)
    for i in range(n):
        bf.add(f"seen-{i}")
    analytic = (1 - math.exp(-k * n / m)) ** k
    trials = 20_000
    fp = sum(1 for i in range(trials) if f"never-{i}" in bf)
    measured = fp / trials
    # measured should be in the analytic ballpark (generous, deterministic seed)
    assert measured < 3 * analytic + 0.01
    assert measured > analytic / 5


def test_deterministic_with_seed():
    a = BloomFilter(m_bits=4096, k=3, seed=1)
    b = BloomFilter(m_bits=4096, k=3, seed=1)
    for i in range(500):
        a.add(f"x{i}"); b.add(f"x{i}")
    assert bytes(a.bits) == bytes(b.bits)
