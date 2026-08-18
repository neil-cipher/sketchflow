"""Tests for step 13: benchmark harness v1.

Gate: harness runs headless, writes report/results.csv with error+memory columns.

These tests verify:
1. run_benchmark() produces correct BenchRow objects (headless, no stdin)
2. write_csv() creates a valid CSV with the required columns
3. Error columns are non-negative and memory columns are positive
4. CU-CMS mean_abs_error <= CMS mean_abs_error (conservative update helps)
5. Results are reproducible (same seed → same output)
6. CSV round-trips: what we write is what we'd read back
"""

import csv
from pathlib import Path

import pytest

from sketchflow.bench import (
    BenchRow, CSV_COLUMNS, run_benchmark, write_csv, main,
)


# ── Use small parameters so tests run fast ───────────────────────────

FAST_KWARGS = dict(
    n_items=5_000,
    universe=500,
    alpha=1.2,
    seed=42,
    epsilons=(0.01,),
    delta=0.01,
    top_k=10,
)


@pytest.fixture
def bench_rows():
    """Run benchmark once with fast params, cache for the session."""
    return run_benchmark(**FAST_KWARGS)


# ── 1. Headless run produces rows ────────────────────────────────────

def test_run_benchmark_returns_rows(bench_rows):
    """run_benchmark() returns a non-empty list of BenchRow."""
    assert len(bench_rows) > 0
    for row in bench_rows:
        assert isinstance(row, BenchRow)


def test_four_variants_per_epsilon(bench_rows):
    """Each epsilon produces exactly four variants."""
    variants = [r.variant for r in bench_rows]
    assert variants == ["CMS", "CU-CMS", "Engine", "Engine-CU"]


# ── 2. CSV output ────────────────────────────────────────────────────

def test_write_csv_creates_file(bench_rows, tmp_path):
    """write_csv() writes a valid CSV with the required columns."""
    csv_path = tmp_path / "report" / "results.csv"
    result = write_csv(bench_rows, csv_path)
    assert result == csv_path
    assert csv_path.exists()

    with open(csv_path) as f:
        reader = csv.DictReader(f)
        assert list(reader.fieldnames) == CSV_COLUMNS
        rows_read = list(reader)
    assert len(rows_read) == len(bench_rows)


def test_csv_has_error_and_memory_columns(bench_rows, tmp_path):
    """The CSV must include error columns and memory columns (the gate)."""
    csv_path = tmp_path / "results.csv"
    write_csv(bench_rows, csv_path)

    with open(csv_path) as f:
        header = f.readline().strip().split(",")

    error_cols = {"mean_abs_error", "max_abs_error", "p99_abs_error", "mean_rel_error"}
    memory_cols = {"sketch_bytes", "baseline_bytes", "memory_ratio"}
    assert error_cols.issubset(set(header)), f"missing error columns: {error_cols - set(header)}"
    assert memory_cols.issubset(set(header)), f"missing memory columns: {memory_cols - set(header)}"


# ── 3. Sanity: error and memory values ──────────────────────────────

def test_errors_are_non_negative(bench_rows):
    """Sketch errors are >= 0 (CMS never undercounts)."""
    for row in bench_rows:
        assert row.mean_abs_error >= 0, f"{row.variant}: negative mean_abs_error"
        assert row.max_abs_error >= 0, f"{row.variant}: negative max_abs_error"
        assert row.p99_abs_error >= 0, f"{row.variant}: negative p99_abs_error"
        assert row.mean_rel_error >= 0, f"{row.variant}: negative mean_rel_error"


def test_memory_positive(bench_rows):
    """Sketch and baseline memory are > 0."""
    for row in bench_rows:
        assert row.sketch_bytes > 0, f"{row.variant}: zero sketch_bytes"
        assert row.baseline_bytes > 0, f"{row.variant}: zero baseline_bytes"
        assert row.memory_ratio > 0, f"{row.variant}: zero memory_ratio"


def test_top_10_hits_in_range(bench_rows):
    """top_10_hits is between 0 and 10."""
    for row in bench_rows:
        assert 0 <= row.top_10_hits <= 10, f"{row.variant}: top_10_hits={row.top_10_hits}"


def test_distinct_keys_consistent(bench_rows):
    """All rows for the same stream should report the same distinct_keys."""
    dk_values = {r.distinct_keys for r in bench_rows}
    assert len(dk_values) == 1, f"inconsistent distinct_keys across rows: {dk_values}"


# ── 4. CU-CMS reduces error ─────────────────────────────────────────

def test_cu_reduces_overestimation(bench_rows):
    """CU-CMS mean_abs_error <= plain CMS mean_abs_error."""
    cms_row = next(r for r in bench_rows if r.variant == "CMS")
    cu_row = next(r for r in bench_rows if r.variant == "CU-CMS")
    assert cu_row.mean_abs_error <= cms_row.mean_abs_error, (
        f"CU-CMS ({cu_row.mean_abs_error}) should be <= CMS ({cms_row.mean_abs_error})"
    )


def test_engine_cu_reduces_overestimation(bench_rows):
    """Engine-CU mean_abs_error <= Engine mean_abs_error."""
    eng_row = next(r for r in bench_rows if r.variant == "Engine")
    eng_cu_row = next(r for r in bench_rows if r.variant == "Engine-CU")
    assert eng_cu_row.mean_abs_error <= eng_row.mean_abs_error, (
        f"Engine-CU ({eng_cu_row.mean_abs_error}) should be <= Engine ({eng_row.mean_abs_error})"
    )


# ── 5. Reproducibility ──────────────────────────────────────────────

def test_reproducible(bench_rows):
    """Same seed → identical results."""
    rows2 = run_benchmark(**FAST_KWARGS)
    assert len(rows2) == len(bench_rows)
    for r1, r2 in zip(bench_rows, rows2):
        assert r1 == r2, f"non-reproducible: {r1.variant} differs on re-run"


# ── 6. CLI entry point ──────────────────────────────────────────────

def test_main_writes_csv(tmp_path, monkeypatch):
    """main() runs headless and writes the CSV."""
    outdir = tmp_path / "bench_out"
    # Patch run_benchmark to use fast params
    import sketchflow.bench as bench_mod
    original_run = bench_mod.run_benchmark

    def fast_run():
        return original_run(**FAST_KWARGS)

    monkeypatch.setattr(bench_mod, "run_benchmark", fast_run)
    main(["--outdir", str(outdir)])
    csv_path = outdir / "results.csv"
    assert csv_path.exists()
    with open(csv_path) as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    assert len(rows) == 4  # 1 epsilon × 4 variants


# ── 7. Multiple epsilons ────────────────────────────────────────────

def test_multiple_epsilons():
    """Running with two epsilons produces 8 rows (4 variants × 2 eps)."""
    rows = run_benchmark(
        n_items=2_000, universe=200, alpha=1.2, seed=7,
        epsilons=(0.01, 0.005), delta=0.01, top_k=5,
    )
    assert len(rows) == 8
    eps_values = sorted(set(r.epsilon for r in rows))
    assert eps_values == [0.005, 0.01]


def test_smaller_epsilon_uses_more_memory():
    """Smaller ε → wider CMS → more sketch_bytes for the same variant."""
    rows = run_benchmark(
        n_items=2_000, universe=200, alpha=1.2, seed=7,
        epsilons=(0.01, 0.001), delta=0.01, top_k=5,
    )
    cms_rows = [r for r in rows if r.variant == "CMS"]
    assert len(cms_rows) == 2
    big_eps = next(r for r in cms_rows if r.epsilon == 0.01)
    small_eps = next(r for r in cms_rows if r.epsilon == 0.001)
    assert small_eps.sketch_bytes > big_eps.sketch_bytes, (
        "smaller ε should use more memory"
    )
    assert small_eps.cms_width > big_eps.cms_width, (
        "smaller ε should produce wider CMS"
    )
