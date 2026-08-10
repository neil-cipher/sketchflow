"""Step 7 gates — CMS memory accounting + serialize / deserialize.

GATE (plan.json step 7):
  - bytes reported == actual
  - round-trip serialize preserves all estimates

Concept: measuring real memory footprint honestly — Python's
list-of-lists-of-ints overhead vs. the packed mathematical minimum.
"""

import sys

import pytest

from sketchflow.baseline import ExactCounter
from sketchflow.cms import CountMinSketch, size_cms
from sketchflow.streams import zipfian_stream


# ── bytes_used() correctness ─────────────────────────────────────

def test_bytes_match_independent_measurement():
    """bytes_used() must equal a fully independent sys.getsizeof walk."""
    cms = CountMinSketch(width=128, depth=4, seed=0)
    for item in zipfian_stream(n_items=1_000, universe=200, seed=99):
        cms.add(item)

    # Independent measurement — same algorithm, different code path.
    actual = sys.getsizeof(cms.rows)
    for row in cms.rows:
        actual += sys.getsizeof(row)
        for cell in row:
            actual += sys.getsizeof(cell)

    assert cms.bytes_used() == actual


def test_bytes_positive_on_fresh_sketch():
    """Even an empty sketch uses memory for its counter matrix."""
    cms = CountMinSketch(width=64, depth=3, seed=0)
    assert cms.bytes_used() > 0


def test_bytes_grow_with_dimensions():
    """A wider/deeper sketch must use more memory."""
    small = CountMinSketch(width=64, depth=2, seed=0)
    large = CountMinSketch(width=256, depth=4, seed=0)
    assert large.bytes_used() > small.bytes_used()


def test_bytes_larger_than_packed_minimum():
    """Python overhead makes bytes_used > depth*width*8 (packed min)."""
    cms = CountMinSketch(width=100, depth=5, seed=0)
    packed_min = 100 * 5 * 8  # 4000 bytes (C-array equivalent)
    assert cms.bytes_used() > packed_min


# ── to_bytes() / from_bytes() round-trip ─────────────────────────

def test_roundtrip_empty():
    """An empty sketch survives serialization round-trip."""
    cms = CountMinSketch(width=64, depth=3, seed=42)
    restored = CountMinSketch.from_bytes(cms.to_bytes())
    assert restored.width == cms.width
    assert restored.depth == cms.depth
    assert restored.seed == cms.seed
    assert restored.total == 0


def test_roundtrip_preserves_all_estimates():
    """THE GATE: after add → serialize → deserialize, every query
    result is bit-for-bit identical to the original."""
    w, d = size_cms(0.01, 0.01)
    cms = CountMinSketch(width=w, depth=d, seed=77)
    keys = set()
    for item in zipfian_stream(n_items=5_000, universe=500, seed=123):
        cms.add(item)
        keys.add(item)

    restored = CountMinSketch.from_bytes(cms.to_bytes())

    assert restored.total == cms.total
    for key in keys:
        assert restored.query(key) == cms.query(key), (
            f"query mismatch on {key!r}"
        )


def test_roundtrip_preserves_row_values():
    """row_values() must also survive the round-trip (not just query)."""
    cms = CountMinSketch(width=128, depth=4, seed=55)
    for item in zipfian_stream(n_items=2_000, universe=200, seed=42):
        cms.add(item)

    restored = CountMinSketch.from_bytes(cms.to_bytes())
    # Check a spread of keys — heavy hitters and light ones.
    for i in range(50):
        key = f"item-{i}"
        assert restored.row_values(key) == cms.row_values(key)


def test_blob_size_is_predictable():
    """Serialized size = 24 (header) + depth × width × 8 (counters)."""
    cms = CountMinSketch(width=100, depth=5, seed=0)
    data = cms.to_bytes()
    expected = 24 + 5 * 100 * 8
    assert len(data) == expected


def test_corrupt_blob_too_short():
    """Truncated blob must raise ValueError."""
    cms = CountMinSketch(width=32, depth=2, seed=0)
    data = cms.to_bytes()
    with pytest.raises(ValueError, match="too short"):
        CountMinSketch.from_bytes(data[:10])


def test_corrupt_blob_wrong_size():
    """Blob with extra bytes must raise ValueError."""
    cms = CountMinSketch(width=32, depth=2, seed=0)
    data = cms.to_bytes()
    with pytest.raises(ValueError, match="mismatch"):
        CountMinSketch.from_bytes(data + b"\x00")
