"""Tests for step 14: accuracy-vs-memory sweep and plot.

Gate: report/accuracy_vs_memory.png regenerable from CSV via one command.

These tests verify:
1. run_sweep() produces BenchRow objects across multiple epsilons
2. Smaller ε → more memory AND less error (the space/accuracy curve)
3. CU-CMS error <= CMS error at every epsilon (conservative update helps)
4. sweep CLI writes CSV; plot CLI reads it and writes PNG
5. load_sweep_csv() correctly parses and groups by variant
6. plot_accuracy_vs_memory() produces a non-empty PNG file
7. The PNG is regenerable: CSV → PNG via one command (the gate)
8. Reproducibility: same seed → identical sweep results
"""

import csv
from pathlib import Path

import pytest

from sketchflow.bench import BenchRow, CSV_COLUMNS, write_csv
from sketchflow.sweep import SWEEP_EPSILONS, run_sweep, main as sweep_main
from sketchflow.plot import load_sweep_csv, plot_accuracy_vs_memory, main as plot_main


# ── Fast params for tests (small stream, few epsilons) ─────────────

FAST_SWEEP_KWARGS = dict(
    n_items=2_000,
    universe=200,
    alpha=1.2,
    seed=42,
    delta=0.01,
    top_k=5,
    epsilons=(0.05, 0.01, 0.005, 0.001),
)


@pytest.fixture(scope="module")
def sweep_rows():
    """Run sweep once with fast params, cache for the module."""
    return run_sweep(**FAST_SWEEP_KWARGS)


@pytest.fixture
def sweep_csv(sweep_rows, tmp_path):
    """Write sweep results to a temp CSV, return path."""
    csv_path = tmp_path / "sweep.csv"
    write_csv(sweep_rows, csv_path)
    return csv_path


# ── 1. Sweep produces correct structure ────────────────────────────

def test_sweep_returns_rows(sweep_rows):
    """run_sweep() returns BenchRow objects for each (variant, eps)."""
    expected = len(FAST_SWEEP_KWARGS["epsilons"]) * 4  # 4 variants
    assert len(sweep_rows) == expected
    for row in sweep_rows:
        assert isinstance(row, BenchRow)


def test_sweep_covers_all_epsilons(sweep_rows):
    """Every requested epsilon appears in the results."""
    eps_seen = sorted(set(r.epsilon for r in sweep_rows))
    assert eps_seen == sorted(FAST_SWEEP_KWARGS["epsilons"])


def test_sweep_covers_all_variants(sweep_rows):
    """All four variants appear at each epsilon."""
    for eps in FAST_SWEEP_KWARGS["epsilons"]:
        variants = sorted(r.variant for r in sweep_rows if r.epsilon == eps)
        assert variants == ["CMS", "CU-CMS", "Engine", "Engine-CU"]


# ── 2. Space/accuracy trade-off (the concept) ─────────────────────

def test_smaller_eps_more_memory(sweep_rows):
    """Smaller ε → wider CMS → more sketch_bytes."""
    cms_rows = sorted(
        [r for r in sweep_rows if r.variant == "CMS"],
        key=lambda r: r.epsilon, reverse=True,
    )
    for i in range(len(cms_rows) - 1):
        assert cms_rows[i].sketch_bytes <= cms_rows[i + 1].sketch_bytes, (
            f"ε={cms_rows[i].epsilon} should use <= memory than ε={cms_rows[i+1].epsilon}"
        )


def test_smaller_eps_less_mean_error(sweep_rows):
    """Smaller ε → lower mean_abs_error (error decays with memory)."""
    cms_rows = sorted(
        [r for r in sweep_rows if r.variant == "CMS"],
        key=lambda r: r.epsilon, reverse=True,
    )
    for i in range(len(cms_rows) - 1):
        assert cms_rows[i].mean_abs_error >= cms_rows[i + 1].mean_abs_error, (
            f"ε={cms_rows[i].epsilon} error should be >= ε={cms_rows[i+1].epsilon} error"
        )


# ── 3. CU-CMS reduces error at every epsilon ──────────────────────

def test_cu_beats_cms_at_every_epsilon(sweep_rows):
    """CU-CMS mean_abs_error <= CMS at each epsilon."""
    for eps in FAST_SWEEP_KWARGS["epsilons"]:
        cms = next(r for r in sweep_rows if r.variant == "CMS" and r.epsilon == eps)
        cu = next(r for r in sweep_rows if r.variant == "CU-CMS" and r.epsilon == eps)
        assert cu.mean_abs_error <= cms.mean_abs_error, (
            f"ε={eps}: CU-CMS ({cu.mean_abs_error}) should be <= CMS ({cms.mean_abs_error})"
        )


# ── 4. CSV → load_sweep_csv round-trip ─────────────────────────────

def test_load_sweep_csv(sweep_csv):
    """load_sweep_csv() correctly parses and groups by variant."""
    data = load_sweep_csv(sweep_csv)
    assert set(data.keys()) == {"CMS", "CU-CMS", "Engine", "Engine-CU"}
    n_eps = len(FAST_SWEEP_KWARGS["epsilons"])
    for variant, rows in data.items():
        assert len(rows) == n_eps, f"{variant}: expected {n_eps} rows"
        # Rows should be sorted by sketch_bytes ascending
        for i in range(len(rows) - 1):
            assert rows[i]["sketch_bytes"] <= rows[i + 1]["sketch_bytes"]


def test_csv_values_match(sweep_rows, sweep_csv):
    """Parsed CSV values match the original BenchRow data."""
    data = load_sweep_csv(sweep_csv)
    for variant, parsed_rows in data.items():
        originals = sorted(
            [r for r in sweep_rows if r.variant == variant],
            key=lambda r: r.epsilon, reverse=True,
        )
        assert len(parsed_rows) == len(originals)
        for pr, orig in zip(parsed_rows, originals):
            assert pr["epsilon"] == orig.epsilon
            assert pr["sketch_bytes"] == orig.sketch_bytes
            assert pr["mean_abs_error"] == orig.mean_abs_error


# ── 5. Plot generation ─────────────────────────────────────────────

def test_plot_creates_png(sweep_csv, tmp_path):
    """plot_accuracy_vs_memory() produces a non-empty PNG file."""
    png_path = tmp_path / "test_plot.png"
    data = load_sweep_csv(sweep_csv)
    result = plot_accuracy_vs_memory(data, png_path)
    assert result == png_path
    assert png_path.exists()
    assert png_path.stat().st_size > 1000, "PNG too small — likely empty"


def test_plot_handles_subset_variants(sweep_csv, tmp_path):
    """Plot still works if only a subset of variants is in the CSV."""
    data = load_sweep_csv(sweep_csv)
    subset = {"CMS": data["CMS"]}
    png_path = tmp_path / "subset.png"
    plot_accuracy_vs_memory(subset, png_path)
    assert png_path.exists()


# ── 6. CLI end-to-end: sweep → CSV → plot → PNG (the gate) ────────

def test_sweep_cli_writes_csv(tmp_path, monkeypatch):
    """sweep CLI writes CSV headlessly."""
    import sketchflow.sweep as sweep_mod
    original = sweep_mod.run_sweep

    def fast_sweep():
        return original(**FAST_SWEEP_KWARGS)

    monkeypatch.setattr(sweep_mod, "run_sweep", fast_sweep)
    sweep_main(["--outdir", str(tmp_path)])
    csv_path = tmp_path / "sweep.csv"
    assert csv_path.exists()
    with open(csv_path) as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    n_eps = len(FAST_SWEEP_KWARGS["epsilons"])
    assert len(rows) == n_eps * 4


def test_plot_cli_regenerates_png(sweep_csv, tmp_path):
    """plot CLI reads CSV and writes PNG — the gate's one-command regen."""
    png_path = tmp_path / "regen.png"
    plot_main(["--csv", str(sweep_csv), "--out", str(png_path)])
    assert png_path.exists()
    assert png_path.stat().st_size > 1000


# ── 7. Reproducibility ────────────────────────────────────────────

def test_sweep_reproducible(sweep_rows):
    """Same seed → identical sweep results."""
    rows2 = run_sweep(**FAST_SWEEP_KWARGS)
    assert len(rows2) == len(sweep_rows)
    for r1, r2 in zip(sweep_rows, rows2):
        assert r1 == r2, f"non-reproducible: {r1.variant} ε={r1.epsilon}"


# ── 8. Default SWEEP_EPSILONS sanity ──────────────────────────────

def test_default_epsilons_ordered():
    """Default SWEEP_EPSILONS are in descending order (widest→narrowest)."""
    for i in range(len(SWEEP_EPSILONS) - 1):
        assert SWEEP_EPSILONS[i] > SWEEP_EPSILONS[i + 1]


def test_default_epsilons_span_two_orders():
    """Sweep covers at least two orders of magnitude."""
    ratio = SWEEP_EPSILONS[0] / SWEEP_EPSILONS[-1]
    assert ratio >= 100, f"ratio {ratio} < 100 (need ≥ two orders of magnitude)"
