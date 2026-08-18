"""Benchmark harness v1 — exact baseline vs sketch variants on synthetic streams.

Runs seeded Zipfian streams through each sketch variant, measures per-key
estimation error and memory footprint against the ExactCounter ground truth,
and writes a tidy CSV to ``report/results.csv``.

Step 13 of plan.json (Phase P4: Benchmark harness + real backbone data).
Gate: harness runs headless, writes report/results.csv with error+memory columns.
Concept: reproducible experiment design.

Usage (headless — no prompts, no GUI)::

    python -m sketchflow.bench                    # default params
    python -m sketchflow.bench --outdir report    # explicit output dir

Reference: methodology follows the reproducible-benchmarking conventions
of Cormode & Muthukrishnan 2005 §6 (synthetic Zipfian evaluation) —
vary ε at fixed δ, report per-key error statistics and memory.
"""

from __future__ import annotations

import csv
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

from sketchflow.baseline import ExactCounter
from sketchflow.cms import CountMinSketch, size_cms
from sketchflow.cu_cms import ConservativeUpdateCMS
from sketchflow.engine import SketchEngine
from sketchflow.streams import zipfian_stream

__all__ = ["BenchRow", "run_benchmark", "write_csv"]

# ── CSV column order (the gate requires "error + memory columns") ────

CSV_COLUMNS = [
    "variant", "epsilon", "delta", "stream_n", "universe", "alpha", "seed",
    "cms_width", "cms_depth", "distinct_keys",
    "mean_abs_error", "max_abs_error", "p99_abs_error",
    "mean_rel_error", "top_10_hits",
    "sketch_bytes", "baseline_bytes", "memory_ratio",
]


# ── Result row ───────────────────────────────────────────────────────

@dataclass
class BenchRow:
    """One row of report/results.csv."""

    variant: str          # "CMS", "CU-CMS", "Engine", "Engine-CU"
    epsilon: float        # CMS ε
    delta: float          # CMS δ
    stream_n: int         # stream length N
    universe: int         # Zipf universe size
    alpha: float          # Zipf exponent
    seed: int             # RNG seed (reproducibility)
    cms_width: int        # CMS table width  (= ceil(e/ε))
    cms_depth: int        # CMS table depth  (= ceil(ln(1/δ)))
    distinct_keys: int    # unique keys in stream
    mean_abs_error: float  # mean |estimate − true| over all distinct keys
    max_abs_error: int     # worst-case absolute error
    p99_abs_error: float   # 99th-percentile absolute error
    mean_rel_error: float  # mean (est − true)/true, keys with true > 0
    top_10_hits: int       # of the true top-10, how many did the variant find
    sketch_bytes: int      # sketch memory footprint (Python)
    baseline_bytes: int    # ExactCounter memory footprint (Python)
    memory_ratio: float    # sketch_bytes / baseline_bytes


# ── Internal helpers ─────────────────────────────────────────────────

def _baseline_bytes(exact: ExactCounter) -> int:
    """Measure Python memory of the ExactCounter dict."""
    total = sys.getsizeof(exact.counts)
    for k, v in exact.counts.items():
        total += sys.getsizeof(k) + sys.getsizeof(v)
    return total


def _engine_bytes(engine: SketchEngine) -> int:
    """CMS bytes_used() + measured SpaceSaving memory."""
    total = engine.cms.bytes_used()
    ss = engine.tracker
    total += sys.getsizeof(ss._heap) + sys.getsizeof(ss._index)
    total += sys.getsizeof(ss.counters)
    for entry in ss._heap:
        total += sys.getsizeof(entry)
        for item in entry:
            total += sys.getsizeof(item)
    for k in ss.counters:
        total += sys.getsizeof(k) + sys.getsizeof(ss.counters[k])
    return total


def _error_stats(abs_errors: list[int]) -> tuple[float, int, float]:
    """Return (mean, max, p99) from absolute-error list."""
    if not abs_errors:
        return 0.0, 0, 0.0
    mean_e = sum(abs_errors) / len(abs_errors)
    max_e = max(abs_errors)
    sorted_e = sorted(abs_errors)
    p99_idx = min(int(len(sorted_e) * 0.99), len(sorted_e) - 1)
    return mean_e, max_e, float(sorted_e[p99_idx])


def _measure_variant(
    variant: str,
    query_fn,
    sketch_bytes: int,
    exact: ExactCounter,
    bl_bytes: int,
    eps: float, delta: float,
    width: int, depth: int,
    n_items: int, universe: int, alpha: float, seed: int,
    top_keys: list[str] | None = None,
    top_k: int = 10,
) -> BenchRow:
    """Measure one variant against the exact baseline."""
    all_keys = list(exact.counts.keys())
    true_top = [k for k, _ in exact.top_k(top_k)]

    # Per-key error
    abs_errors: list[int] = []
    rel_errors: list[float] = []
    for key in all_keys:
        true_c = exact.query(key)
        est_c = query_fn(key)
        err = abs(est_c - true_c)
        abs_errors.append(err)
        if true_c > 0:
            rel_errors.append(err / true_c)

    mean_abs, max_abs, p99_abs = _error_stats(abs_errors)
    mean_rel = sum(rel_errors) / len(rel_errors) if rel_errors else 0.0

    # Top-k precision
    if top_keys is None:
        # For raw CMS/CU-CMS: query all keys and pick the top estimates
        estimates = sorted(
            ((key, query_fn(key)) for key in all_keys),
            key=lambda kv: (-kv[1], kv[0]),
        )
        top_keys = [k for k, _ in estimates[:top_k]]
    hits = len(set(top_keys) & set(true_top))

    mem_ratio = sketch_bytes / bl_bytes if bl_bytes > 0 else 0.0

    return BenchRow(
        variant=variant,
        epsilon=eps, delta=delta,
        stream_n=n_items, universe=universe, alpha=alpha, seed=seed,
        cms_width=width, cms_depth=depth,
        distinct_keys=exact.distinct_keys(),
        mean_abs_error=round(mean_abs, 4),
        max_abs_error=max_abs,
        p99_abs_error=round(p99_abs, 4),
        mean_rel_error=round(mean_rel, 6),
        top_10_hits=hits,
        sketch_bytes=sketch_bytes,
        baseline_bytes=bl_bytes,
        memory_ratio=round(mem_ratio, 4),
    )


# ── Public API ───────────────────────────────────────────────────────

def run_benchmark(
    n_items: int = 50_000,
    universe: int = 5_000,
    alpha: float = 1.2,
    seed: int = 42,
    epsilons: tuple[float, ...] = (0.01, 0.005, 0.001),
    delta: float = 0.01,
    top_k: int = 10,
) -> list[BenchRow]:
    """Run the full benchmark suite and return result rows.

    For each epsilon value, feeds the same seeded Zipfian stream through
    four variants (CMS, CU-CMS, Engine, Engine-CU) and measures per-key
    error and memory against the ExactCounter ground truth.

    Parameters
    ----------
    n_items : int
        Stream length (number of add() calls).
    universe : int
        Number of distinct keys in the Zipf distribution.
    alpha : float
        Zipf exponent (higher = more skewed).
    seed : int
        RNG seed for the stream generator.
    epsilons : tuple of float
        CMS ε values to sweep.  Smaller ε → wider CMS → less error → more memory.
    delta : float
        CMS failure probability (fixed across all runs).
    top_k : int
        Number of heavy hitters to track and compare.

    Returns
    -------
    list of BenchRow
        One row per (variant, epsilon) combination.
    """
    rows: list[BenchRow] = []

    for eps in epsilons:
        # Materialise stream (same seed = same stream for fair comparison)
        stream = list(zipfian_stream(
            n_items=n_items, universe=universe, alpha=alpha, seed=seed,
        ))

        # Ground truth
        exact = ExactCounter()
        for item in stream:
            exact.add(item)
        bl_bytes = _baseline_bytes(exact)

        width, depth = size_cms(eps, delta)

        # ── CMS ──────────────────────────────────────────────────────
        cms = CountMinSketch(width=width, depth=depth, seed=seed)
        for item in stream:
            cms.add(item)

        rows.append(_measure_variant(
            "CMS", cms.query, cms.bytes_used(),
            exact, bl_bytes, eps, delta, width, depth,
            n_items, universe, alpha, seed, top_k=top_k,
        ))

        # ── CU-CMS ──────────────────────────────────────────────────
        cu = ConservativeUpdateCMS(width=width, depth=depth, seed=seed)
        for item in stream:
            cu.add(item)

        rows.append(_measure_variant(
            "CU-CMS", cu.query, cu.bytes_used(),
            exact, bl_bytes, eps, delta, width, depth,
            n_items, universe, alpha, seed, top_k=top_k,
        ))

        # ── Engine (CMS + SpaceSaving) ───────────────────────────────
        eng = SketchEngine(
            epsilon=eps, delta=delta, top_k=top_k, seed=seed,
            conservative=False,
        )
        for item in stream:
            eng.add(item)

        eng_top = [k for k, _ in eng.heavy_hitters(top_k)]
        rows.append(_measure_variant(
            "Engine", eng.estimate, _engine_bytes(eng),
            exact, bl_bytes, eps, delta, width, depth,
            n_items, universe, alpha, seed,
            top_keys=eng_top, top_k=top_k,
        ))

        # ── Engine-CU (CU-CMS + SpaceSaving) ────────────────────────
        eng_cu = SketchEngine(
            epsilon=eps, delta=delta, top_k=top_k, seed=seed,
            conservative=True,
        )
        for item in stream:
            eng_cu.add(item)

        eng_cu_top = [k for k, _ in eng_cu.heavy_hitters(top_k)]
        rows.append(_measure_variant(
            "Engine-CU", eng_cu.estimate, _engine_bytes(eng_cu),
            exact, bl_bytes, eps, delta, width, depth,
            n_items, universe, alpha, seed,
            top_keys=eng_cu_top, top_k=top_k,
        ))

    return rows


def write_csv(rows: list[BenchRow], path: Path) -> Path:
    """Write benchmark rows to a CSV file.

    Creates parent directories if needed.  Returns the path written.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))
    return path


# ── CLI entry point (python -m sketchflow.bench) ─────────────────────

def main(argv: list[str] | None = None) -> None:
    """Run the benchmark and write report/results.csv."""
    import argparse

    parser = argparse.ArgumentParser(
        description="SketchFlow benchmark harness v1",
    )
    parser.add_argument(
        "--outdir", type=str, default="report",
        help="output directory for results.csv (default: report)",
    )
    args = parser.parse_args(argv)

    outpath = Path(args.outdir) / "results.csv"
    print(f"Running benchmark harness v1 …")
    rows = run_benchmark()
    write_csv(rows, outpath)
    print(f"Wrote {len(rows)} rows to {outpath}")
    print(f"Variants: {sorted(set(r.variant for r in rows))}")
    print(f"Epsilons: {sorted(set(r.epsilon for r in rows))}")


if __name__ == "__main__":
    main()
