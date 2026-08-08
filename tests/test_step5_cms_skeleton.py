"""Step 5 gates — CMS skeleton.

GATE (plan.json step 5): after adds, every row cell for an item is
>= its true count (the never-undercount invariant), checked on a
10k-item Zipfian stream against the exact baseline.
"""

import pytest

from sketchflow.baseline import ExactCounter
from sketchflow.cms import CountMinSketch
from sketchflow.streams import zipfian_stream


def test_rejects_bad_shape():
    with pytest.raises(ValueError):
        CountMinSketch(width=0, depth=4)
    with pytest.raises(ValueError):
        CountMinSketch(width=16, depth=0)


def test_gate_never_undercounts_on_zipfian_stream():
    """THE step-5 gate: 10k-item seeded Zipfian stream, deliberately
    small sketch (lots of collisions) — every one of the depth
    counters for every seen key must still be >= its true count."""
    cms = CountMinSketch(width=256, depth=4, seed=42)
    exact = ExactCounter()
    for item in zipfian_stream(n_items=10_000, universe=1_000, alpha=1.2, seed=42):
        cms.add(item)
        exact.add(item)

    assert cms.total == 10_000
    assert exact.distinct_keys() > 0  # API note: returns the COUNT of keys
    for key, truth in exact.top_k(exact.distinct_keys()):
        for cell in cms.row_values(key):
            assert cell >= truth, (
                f"undercount: {key} true={truth} cell={cell}"
            )


def test_collisions_only_inflate():
    # With width 8 and many keys, collisions are guaranteed; the
    # invariant must survive them (that is the whole point).
    cms = CountMinSketch(width=8, depth=3, seed=7)
    for i in range(500):
        cms.add(f"k{i % 40}")
    for i in range(40):
        assert all(cell >= 500 // 40 for cell in cms.row_values(f"k{i}"))


def test_weighted_add_and_determinism():
    a = CountMinSketch(width=64, depth=4, seed=11)
    b = CountMinSketch(width=64, depth=4, seed=11)
    for sketch in (a, b):
        sketch.add("x", count=5)
        sketch.add("y")
    assert a.rows == b.rows  # same seed -> identical matrix
    assert a.total == 6
    assert all(cell >= 5 for cell in a.row_values("x"))
    with pytest.raises(ValueError):
        a.add("z", count=-1)
