"""Step 1 gates: seeded stream reproducibility + baseline exactness."""
from collections import Counter

from sketchflow.baseline import ExactCounter
from sketchflow.streams import zipfian_stream


def test_same_seed_same_stream():
    a = list(zipfian_stream(n_items=5000, seed=7))
    b = list(zipfian_stream(n_items=5000, seed=7))
    assert a == b  # reproducible ground truth is the whole point


def test_baseline_matches_collections_counter():
    stream = list(zipfian_stream(n_items=20_000, universe=500, seed=42))
    ec = ExactCounter()
    for key in stream:
        ec.add(key)
    ref = Counter(stream)
    assert ec.total == len(stream)
    assert ec.distinct_keys() == len(ref)
    for key, true_count in ref.items():
        assert ec.query(key) == true_count
    assert ec.query("never-seen") == 0


def test_stream_is_heavy_tailed():
    ec = ExactCounter()
    for key in zipfian_stream(n_items=50_000, universe=1000, alpha=1.2, seed=1):
        ec.add(key)
    top = ec.top_k(50)
    # rank-1 should dominate rank-50 by a wide margin under Zipf
    assert top[0][1] > 4 * top[-1][1]
