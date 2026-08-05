"""Step 2 gates: determinism, uniform spread, independence sanity."""
from collections import Counter

from sketchflow.hashing import HashFamily


def test_deterministic_and_seed_sensitive():
    a = HashFamily(k=3, width=100, seed=7)
    b = HashFamily(k=3, width=100, seed=7)
    c = HashFamily(k=3, width=100, seed=8)
    keys = [f"flow-{i}" for i in range(200)]
    assert [a.buckets(k) for k in keys] == [b.buckets(k) for k in keys]
    assert any(a.buckets(k) != c.buckets(k) for k in keys)


def test_uniform_spread():
    # 20k distinct keys into 64 buckets: each bucket should get ~312.
    fam = HashFamily(k=1, width=64, seed=42)
    counts = Counter(fam.bucket(0, f"key-{i}") for i in range(20_000))
    expected = 20_000 / 64
    chi2 = sum((counts.get(bkt, 0) - expected) ** 2 / expected for bkt in range(64))
    assert chi2 < 150  # far below a suspicious spread for df=63


def test_functions_are_independent_ish():
    # Joint spread of (f0, f1) over an 8x8 grid should also be uniform-ish;
    # if the two functions were correlated, the grid would clump.
    fam = HashFamily(k=2, width=8, seed=42)
    joint = Counter((fam.bucket(0, f"k{i}"), fam.bucket(1, f"k{i}")) for i in range(12_800))
    expected = 12_800 / 64
    chi2 = sum((joint.get((r, c), 0) - expected) ** 2 / expected for r in range(8) for c in range(8))
    assert chi2 < 160


def test_functions_differ_from_each_other():
    fam = HashFamily(k=4, width=1000, seed=1)
    same = sum(1 for i in range(500) if len(set(fam.buckets(f"x{i}"))) == 1)
    assert same < 5  # 4 hashes agreeing on one bucket should be vanishingly rare
