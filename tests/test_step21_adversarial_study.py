"""Step 21 gate: CU vs plain CMS under adversarial load.

plan.json step 21 gate: "artifact: report/adversarial.csv comparing
violation rates; finding written to decisions.log".

The core empirical finding under test: conservative update does NOT
survive a full-row collision attack. Every member of a full-row
collision group shares its bucket in EVERY row, so CU's add() finds
min == all of the group's cells and bumps them together -- the group's
counters rise in lock-step exactly like plain CMS. On the benign
control stream CU keeps its usual advantage (step 9's result).
"""

import csv
import os

import pytest

from sketchflow.adversarial_study import (
    CSV_COLUMNS,
    adversarial_cu_study,
    write_adversarial_csv,
)

# Small-but-decisive parameters for CI speed: the step-19/20 demo sketch.
DEMO = dict(width=16, depth=3, num_groups=5, group_size=5, events_per_key=20, epsilon=0.02)


def _rows(seeds):
    return adversarial_cu_study(seeds=seeds, **DEMO)


def _get(rows, seed, variant, stream):
    (row,) = [
        r
        for r in rows
        if r["seed"] == seed and r["variant"] == variant and r["stream"] == stream
    ]
    return row


def test_cu_does_not_survive_full_row_attack_single_seed():
    """Seed 42 (the step-20 demo): CU's violation rate on the adversarial
    stream is just as total as plain CMS's -- every colliding key breaks
    the eps*N bound in both variants."""
    rows = _rows(seeds=[42])
    plain = _get(rows, 42, "cms", "adversarial")
    cu = _get(rows, 42, "cu", "adversarial")
    assert plain["violation_rate"] == 1.0
    assert cu["violation_rate"] == 1.0
    # CU's error stays essentially at plain-CMS level: no rescue.
    assert cu["mean_error"] >= 0.9 * plain["mean_error"]
    # Each group member absorbed (at least) its whole group's traffic:
    # true=20 events but estimate >= group total of 100 -> error >= 80.
    assert cu["mean_error"] >= 80.0


def test_cu_keeps_its_edge_on_the_benign_control():
    """Same seeds, same memory: on the control stream CU is never worse
    than plain CMS, and strictly better in aggregate (step 9's advantage
    is real -- it just doesn't apply to full-row colliders)."""
    seeds = [0, 1, 42]
    rows = _rows(seeds=seeds)
    total_plain = total_cu = 0.0
    for seed in seeds:
        plain = _get(rows, seed, "cms", "control")
        cu = _get(rows, seed, "cu", "control")
        assert cu["mean_error"] <= plain["mean_error"]
        assert cu["violation_rate"] <= plain["violation_rate"]
        total_plain += plain["mean_error"]
        total_cu += cu["mean_error"]
    assert total_cu < total_plain


def test_attack_beats_control_for_both_variants():
    """The attack raises error above the control for plain AND CU at the
    identical memory budget -- CU is not a defense."""
    rows = _rows(seeds=[0, 1, 42])
    for seed in (0, 1, 42):
        for variant in ("cms", "cu"):
            adv = _get(rows, seed, variant, "adversarial")
            ctl = _get(rows, seed, variant, "control")
            assert adv["mean_error"] > ctl["mean_error"]
            assert adv["violation_rate"] >= ctl["violation_rate"]


def test_rows_shape_and_bounds():
    rows = _rows(seeds=[0, 1])
    # 2 seeds x 2 variants x 2 streams
    assert len(rows) == 8
    for r in rows:
        assert set(CSV_COLUMNS) <= set(r.keys())
        assert 0.0 <= r["violation_rate"] <= 1.0
        assert r["mean_error"] >= 0.0  # CMS never undercounts
        assert r["n_events"] == 500
        assert r["distinct_keys"] == 25


def test_study_is_deterministic():
    assert _rows(seeds=[7]) == _rows(seeds=[7])


def test_write_csv_roundtrip(tmp_path):
    rows = _rows(seeds=[0])
    path = write_adversarial_csv(rows, path=str(tmp_path / "adversarial.csv"))
    with open(path, newline="") as f:
        read_back = list(csv.DictReader(f))
    assert len(read_back) == len(rows)
    assert list(read_back[0].keys()) == CSV_COLUMNS
    for orig, got in zip(rows, read_back):
        assert float(got["violation_rate"]) == pytest.approx(orig["violation_rate"])
        assert float(got["mean_error"]) == pytest.approx(orig["mean_error"])


def test_committed_artifact_present_and_wellformed():
    """The step-21 gate artifact ships with the repo: report/adversarial.csv,
    regenerable via `PYTHONPATH=src python -m sketchflow.adversarial_study`."""
    path = os.path.join(os.path.dirname(__file__), "..", "report", "adversarial.csv")
    assert os.path.exists(path), "report/adversarial.csv missing (step-21 artifact)"
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    assert list(rows[0].keys()) == CSV_COLUMNS
    # default study: 10 seeds x 2 variants x 2 streams
    assert len(rows) == 40
    adv_cu = [float(r["violation_rate"]) for r in rows if r["variant"] == "cu" and r["stream"] == "adversarial"]
    assert all(v >= 0.5 for v in adv_cu), "committed CSV should show CU failing under attack"
