"""Step 16 tests — CIC-IDS-2017 loader + engine on real flow data.

Gate (plan.json step 16):
  'test: loader parses sample rows; engine top-k over real flows
   matches exact top-k on the sample'

These tests verify:
  1. Loader basics: parses all 10180 rows, yields correct key format
  2. Rich flow loader: port/label/duration fields present and typed
  3. Column-not-found error handling
  4. Engine on real data: top-k ports match exact baseline
  5. CU-CMS variant also matches on real data
  6. Distinct port count matches ground truth
  7. Label distribution matches known sample composition
  8. Attack-port analysis: brute-force flows hit port 80
"""

import os
import pytest
from collections import Counter

# ── Loader under test ────────────────────────────────────────────────
from sketchflow.cicids import (
    load_cicids,
    load_cicids_flows,
    CICIDS_COLUMNS,
    DEFAULT_SAMPLE_PATH,
)

# ── Engine + baseline ────────────────────────────────────────────────
from sketchflow.engine import SketchEngine
from sketchflow.baseline import ExactCounter

# ── Path to the sample CSV ───────────────────────────────────────────
SAMPLE = os.path.normpath(DEFAULT_SAMPLE_PATH)
EXPECTED_ROWS = 10180


@pytest.fixture(scope="module")
def all_keys():
    """Load all stream keys once for the module."""
    return list(load_cicids(SAMPLE))


@pytest.fixture(scope="module")
def all_flows():
    """Load all rich flow dicts once for the module."""
    return list(load_cicids_flows(SAMPLE))


# ── 1. Loader basics ────────────────────────────────────────────────

def test_loader_row_count(all_keys):
    """Loader yields exactly 10180 keys (one per CSV data row)."""
    assert len(all_keys) == EXPECTED_ROWS


def test_loader_key_format(all_keys):
    """Every key has the 'port:<N>' format."""
    for key in all_keys:
        assert key.startswith("port:"), f"Bad key format: {key!r}"
        port_str = key.split(":", 1)[1]
        int(port_str)  # must parse as int


def test_loader_default_path_resolves():
    """DEFAULT_SAMPLE_PATH points to an existing file."""
    assert os.path.isfile(SAMPLE), f"Sample not found at {SAMPLE}"


def test_loader_known_top_port(all_keys):
    """Port 53 (DNS) is the most common key in the sample."""
    counts = Counter(all_keys)
    top_key = counts.most_common(1)[0][0]
    assert top_key == "port:53"


# ── 2. Rich flow loader ─────────────────────────────────────────────

def test_flow_loader_row_count(all_flows):
    """Rich flow loader also yields 10180 dicts."""
    assert len(all_flows) == EXPECTED_ROWS


def test_flow_loader_dict_keys(all_flows):
    """Every flow dict has the expected keys."""
    expected_keys = {"key", "port", "label", "duration", "fwd_pkts", "bwd_pkts"}
    for flow in all_flows[:10]:
        assert set(flow.keys()) == expected_keys


def test_flow_loader_types(all_flows):
    """Port, duration, packet counts are ints; key and label are strings."""
    for flow in all_flows[:50]:
        assert isinstance(flow["key"], str)
        assert isinstance(flow["port"], int)
        assert isinstance(flow["label"], str)
        assert isinstance(flow["duration"], int)
        assert isinstance(flow["fwd_pkts"], int)
        assert isinstance(flow["bwd_pkts"], int)


def test_flow_loader_port_range(all_flows):
    """All ports are valid (0-65535)."""
    for flow in all_flows:
        assert 0 <= flow["port"] <= 65535, f"Invalid port: {flow['port']}"


# ── 3. Error handling ───────────────────────────────────────────────

def test_loader_missing_file():
    """Loader raises FileNotFoundError on a nonexistent path."""
    with pytest.raises(FileNotFoundError):
        list(load_cicids("/nonexistent/path.csv"))


# ── 4. Engine on real data — top-k matches exact baseline ───────────

def test_engine_topk_matches_exact(all_keys):
    """Gate test: engine top-10 ports == exact top-10 ports.

    This is the core gate from plan.json step 16: run the SketchFlow
    engine on real CIC-IDS flow data and verify the heavy hitter
    detection matches the ground truth.
    """
    # Build exact baseline
    exact = ExactCounter()
    for key in all_keys:
        exact.add(key)

    # Build engine.  The sample has 1371 distinct ports with a long tail
    # of low-count ports (positions 7-10 in exact ranking have counts
    # 15-27).  Space-Saving needs k >> distinct count to track the tail
    # accurately, so we use k=500 (guarantee threshold N/k ≈ 20, which
    # covers all top-10 ports).  ε=0.001 keeps CMS estimates tight.
    engine = SketchEngine(epsilon=0.001, delta=0.01, top_k=500, seed=42)
    for key in all_keys:
        engine.add(key)

    # Compare top-5 keys (well-separated counts: port 22 at 49 vs
    # port 137 at 39 — clear gap, no ambiguity from eviction noise)
    exact_top5_keys = set(k for k, _ in exact.top_k(5))
    engine_top5_keys = set(k for k, _ in engine.heavy_hitters(5))
    assert engine_top5_keys == exact_top5_keys, (
        f"Engine top-5 {engine_top5_keys} != exact {exact_top5_keys}"
    )

    # Also check top-10 — with k=500 and tight ε this should pass
    exact_top10_keys = set(k for k, _ in exact.top_k(10))
    engine_top10_keys = set(k for k, _ in engine.heavy_hitters(10))
    assert engine_top10_keys == exact_top10_keys, (
        f"Engine top-10 {engine_top10_keys} != exact {exact_top10_keys}"
    )


def test_engine_estimates_never_undercount(all_keys):
    """Engine estimates are >= true counts (never-undercount invariant)."""
    exact = ExactCounter()
    engine = SketchEngine(epsilon=0.001, delta=0.01, top_k=500, seed=42)
    for key in all_keys:
        exact.add(key)
        engine.add(key)

    for key in exact.counts:
        assert engine.estimate(key) >= exact.query(key), (
            f"Undercount for {key}: engine={engine.estimate(key)} "
            f"< exact={exact.query(key)}"
        )


def test_engine_total_matches(all_keys):
    """Engine total == number of rows ingested."""
    engine = SketchEngine(epsilon=0.001, delta=0.01, top_k=20, seed=42)
    for key in all_keys:
        engine.add(key)
    assert engine.total == EXPECTED_ROWS


# ── 5. CU-CMS variant on real data ──────────────────────────────────

def test_cu_engine_topk_matches_exact(all_keys):
    """CU-CMS engine also matches exact top-10 on real data."""
    exact = ExactCounter()
    engine = SketchEngine(
        epsilon=0.001, delta=0.01, top_k=500, seed=42, conservative=True
    )
    for key in all_keys:
        exact.add(key)
        engine.add(key)

    exact_top10 = set(k for k, _ in exact.top_k(10))
    engine_top10 = set(k for k, _ in engine.heavy_hitters(10))
    assert engine_top10 == exact_top10


def test_cu_reduces_overestimation_real_data(all_keys):
    """CU-CMS overestimates less than plain CMS on real flow data."""
    exact = ExactCounter()
    engine_plain = SketchEngine(epsilon=0.001, delta=0.01, top_k=20, seed=42)
    engine_cu = SketchEngine(
        epsilon=0.001, delta=0.01, top_k=20, seed=42, conservative=True
    )
    for key in all_keys:
        exact.add(key)
        engine_plain.add(key)
        engine_cu.add(key)

    total_over_plain = sum(
        engine_plain.estimate(k) - exact.query(k) for k in exact.counts
    )
    total_over_cu = sum(
        engine_cu.estimate(k) - exact.query(k) for k in exact.counts
    )
    assert total_over_cu < total_over_plain, (
        f"CU overestimation ({total_over_cu}) should be less than "
        f"plain CMS ({total_over_plain})"
    )


# ── 6. Data integrity checks ────────────────────────────────────────

def test_distinct_port_count(all_keys):
    """Sample has 1371 distinct destination ports."""
    distinct = len(set(all_keys))
    assert distinct == 1371, f"Expected 1371 distinct ports, got {distinct}"


def test_label_distribution(all_flows):
    """Label counts match the known sample composition."""
    labels = Counter(f["label"] for f in all_flows)
    assert labels.get("BENIGN", 0) == 8000
    # Attack labels have encoding artifacts; just check totals
    total_attacks = sum(v for k, v in labels.items() if k != "BENIGN")
    assert total_attacks == 2180  # 1507 + 652 + 21


# ── 7. Attack-port analysis ─────────────────────────────────────────

def test_attack_flows_target_http(all_flows):
    """Web attack flows primarily target port 80 (HTTP)."""
    attack_ports = Counter(
        f["port"] for f in all_flows if f["label"] != "BENIGN"
    )
    # Port 80 should be the top attacked port (web attacks target HTTP)
    top_attack_port = attack_ports.most_common(1)[0][0]
    assert top_attack_port == 80, (
        f"Expected port 80 as top attack target, got {top_attack_port}"
    )
