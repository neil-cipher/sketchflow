"""Plot accuracy vs memory from sweep CSV — one-command PNG regeneration.

Step 14 of plan.json (Phase P4: Benchmark harness + real backbone data).
Gate: report/accuracy_vs_memory.png regenerable from CSV via one command.
Concept: reading a space/accuracy curve; reproducibility.

Reads ``report/sweep.csv`` (produced by ``python -m sketchflow.sweep``)
and generates a two-panel figure:

* **Left panel**: mean absolute error vs sketch memory (bytes) —
  how average per-key overestimation drops as you widen the CMS.
* **Right panel**: worst-case (max) absolute error vs sketch memory —
  the tail that matters for anomaly detection.

Both axes use log scale because epsilon spans two orders of magnitude.
Four lines per panel: CMS, CU-CMS, Engine, Engine-CU.

Usage (the gate — one command regenerates the plot from CSV)::

    python -m sketchflow.plot                           # default paths
    python -m sketchflow.plot --csv report/sweep.csv     # explicit input
    python -m sketchflow.plot --out report/my_plot.png   # explicit output

Reference: visualisation follows the style of Cormode & Muthukrishnan
2005 §6 Figures 3–5 (error vs space on log scales).
"""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # headless — no GUI required
import matplotlib.pyplot as plt

__all__ = ["load_sweep_csv", "plot_accuracy_vs_memory"]

# Consistent colours per variant (colourblind-friendly palette)
VARIANT_STYLE: dict[str, dict] = {
    "CMS":       {"color": "#1f77b4", "marker": "o", "linestyle": "-"},
    "CU-CMS":    {"color": "#ff7f0e", "marker": "s", "linestyle": "-"},
    "Engine":    {"color": "#1f77b4", "marker": "o", "linestyle": "--"},
    "Engine-CU": {"color": "#ff7f0e", "marker": "s", "linestyle": "--"},
}

# Canonical variant order for the legend
VARIANT_ORDER = ["CMS", "CU-CMS", "Engine", "Engine-CU"]


def load_sweep_csv(csv_path: Path) -> dict[str, list[dict]]:
    """Load sweep CSV and group rows by variant.

    Returns
    -------
    dict mapping variant name → list of row dicts (sorted by sketch_bytes).
    """
    by_variant: dict[str, list[dict]] = defaultdict(list)
    with open(csv_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Convert numeric fields
            parsed = {
                "epsilon": float(row["epsilon"]),
                "sketch_bytes": int(row["sketch_bytes"]),
                "mean_abs_error": float(row["mean_abs_error"]),
                "max_abs_error": int(row["max_abs_error"]),
                "p99_abs_error": float(row["p99_abs_error"]),
                "mean_rel_error": float(row["mean_rel_error"]),
                "memory_ratio": float(row["memory_ratio"]),
                "cms_width": int(row["cms_width"]),
                "cms_depth": int(row["cms_depth"]),
            }
            by_variant[row["variant"]].append(parsed)

    # Sort each variant's rows by sketch_bytes (ascending memory)
    for variant in by_variant:
        by_variant[variant].sort(key=lambda r: r["sketch_bytes"])

    return dict(by_variant)


def plot_accuracy_vs_memory(
    data: dict[str, list[dict]],
    out_path: Path,
    title: str = "SketchFlow: Accuracy vs Memory",
) -> Path:
    """Generate the two-panel accuracy-vs-memory figure.

    Parameters
    ----------
    data : dict
        Output of load_sweep_csv().
    out_path : Path
        Where to save the PNG.
    title : str
        Figure suptitle.

    Returns
    -------
    Path to the saved PNG.
    """
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
    fig.suptitle(title, fontsize=14, fontweight="bold")

    for variant in VARIANT_ORDER:
        if variant not in data:
            continue
        rows = data[variant]
        xs = [r["sketch_bytes"] for r in rows]
        style = VARIANT_STYLE.get(variant, {"color": "grey", "marker": "x"})

        # Left panel: mean absolute error
        ys_mean = [r["mean_abs_error"] for r in rows]
        ax1.plot(xs, ys_mean, label=variant, markersize=5, **style)

        # Right panel: max absolute error
        ys_max = [r["max_abs_error"] for r in rows]
        ax2.plot(xs, ys_max, label=variant, markersize=5, **style)

    # Format left panel
    ax1.set_xlabel("Sketch memory (bytes)", fontsize=11)
    ax1.set_ylabel("Mean absolute error", fontsize=11)
    ax1.set_xscale("log")
    ax1.set_yscale("log")
    ax1.legend(fontsize=9)
    ax1.grid(True, which="both", alpha=0.3)
    ax1.set_title("Mean error decay", fontsize=11)

    # Format right panel
    ax2.set_xlabel("Sketch memory (bytes)", fontsize=11)
    ax2.set_ylabel("Max absolute error", fontsize=11)
    ax2.set_xscale("log")
    ax2.set_yscale("log")
    ax2.legend(fontsize=9)
    ax2.grid(True, which="both", alpha=0.3)
    ax2.set_title("Worst-case error decay", fontsize=11)

    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(out_path), dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path


# ── CLI entry point (python -m sketchflow.plot) ──────────────────────

def main(argv: list[str] | None = None) -> None:
    """Regenerate accuracy_vs_memory.png from sweep CSV."""
    import argparse

    parser = argparse.ArgumentParser(
        description="SketchFlow accuracy-vs-memory plot (step 14)",
    )
    parser.add_argument(
        "--csv", type=str, default="report/sweep.csv",
        help="input CSV path (default: report/sweep.csv)",
    )
    parser.add_argument(
        "--out", type=str, default="report/accuracy_vs_memory.png",
        help="output PNG path (default: report/accuracy_vs_memory.png)",
    )
    args = parser.parse_args(argv)

    csv_path = Path(args.csv)
    out_path = Path(args.out)

    if not csv_path.exists():
        print(f"Error: {csv_path} not found. Run `python -m sketchflow.sweep` first.")
        raise SystemExit(1)

    print(f"Reading {csv_path} …")
    data = load_sweep_csv(csv_path)
    print(f"Variants: {sorted(data.keys())}")
    print(f"Points per variant: {[len(v) for v in data.values()]}")

    plot_accuracy_vs_memory(data, out_path)
    print(f"Saved {out_path}")


if __name__ == "__main__":
    main()
