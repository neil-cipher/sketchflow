"""Accuracy-vs-memory sweep — vary ε to trace error decay as memory grows.

Step 14 of plan.json (Phase P4: Benchmark harness + real backbone data).
Gate: report/accuracy_vs_memory.png regenerable from CSV via one command.
Concept: reading a space/accuracy curve; reproducibility.

Feeds the same seeded Zipfian stream through CMS and CU-CMS at eight
epsilon values spanning two orders of magnitude.  As ε shrinks the CMS
widens (width = ⌈e/ε⌉), memory grows, and per-key error decays — the
fundamental space/accuracy trade-off of sketching.

Usage::

    python -m sketchflow.sweep                 # write report/sweep.csv
    python -m sketchflow.sweep --outdir report  # explicit output dir

Then regenerate the plot from the CSV::

    python -m sketchflow.plot                  # → report/accuracy_vs_memory.png

Reference: the sweep methodology mirrors Cormode & Muthukrishnan 2005 §6
(vary ε at fixed δ, measure per-key error statistics and memory).
"""

from __future__ import annotations

from pathlib import Path

from sketchflow.bench import BenchRow, run_benchmark, write_csv

__all__ = ["SWEEP_EPSILONS", "run_sweep"]

# Eight points spanning ε = 0.1 … 0.0005 (two orders of magnitude).
# This produces 8 × 4 variants = 32 CSV rows — enough for a smooth curve.
SWEEP_EPSILONS: tuple[float, ...] = (
    0.1, 0.05, 0.02, 0.01, 0.005, 0.002, 0.001, 0.0005,
)


def run_sweep(
    n_items: int = 50_000,
    universe: int = 5_000,
    alpha: float = 1.2,
    seed: int = 42,
    delta: float = 0.01,
    top_k: int = 10,
    epsilons: tuple[float, ...] | None = None,
) -> list[BenchRow]:
    """Run accuracy-vs-memory sweep across a range of epsilon values.

    Parameters
    ----------
    epsilons : tuple of float, optional
        Override the default sweep epsilon set.

    Returns
    -------
    list of BenchRow
        One row per (variant, epsilon) combination.
    """
    eps = epsilons if epsilons is not None else SWEEP_EPSILONS
    return run_benchmark(
        n_items=n_items,
        universe=universe,
        alpha=alpha,
        seed=seed,
        epsilons=eps,
        delta=delta,
        top_k=top_k,
    )


# ── CLI entry point (python -m sketchflow.sweep) ──────────────────────

def main(argv: list[str] | None = None) -> None:
    """Run the sweep and write report/sweep.csv."""
    import argparse

    parser = argparse.ArgumentParser(
        description="SketchFlow accuracy-vs-memory sweep (step 14)",
    )
    parser.add_argument(
        "--outdir", type=str, default="report",
        help="output directory for sweep.csv (default: report)",
    )
    args = parser.parse_args(argv)

    outpath = Path(args.outdir) / "sweep.csv"
    print("Running accuracy-vs-memory sweep …")
    rows = run_sweep()
    write_csv(rows, outpath)
    print(f"Wrote {len(rows)} rows to {outpath}")
    print(f"Epsilons: {sorted(set(r.epsilon for r in rows))}")
    print(f"Variants: {sorted(set(r.variant for r in rows))}")


if __name__ == "__main__":
    main()
