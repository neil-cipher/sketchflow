"""Plot the real-trace adversarial study — one-command PNG regeneration.

Step 22 of plan.json (Phase P5: Adversarial stress). Gate artifact:
``report/real_adversarial.png``, regenerable from the two real traces
via one command::

    PYTHONPATH=src python -m sketchflow.real_plot

The command loads the MAWI backbone pcap (step 18) and the CIC-IDS-2017
flow sample (step 16), runs ``sketchflow.real_adversary``'s heavy-hitter
amplification study on each, writes ``report/real_adversarial.csv``, and
renders a two-panel figure:

* **Left panel** — violation rate vs amplification factor. Two lines per
  trace: the *provisioned* bound (ε·N₀, the operator's fixed promise —
  solid) climbs as the attack strengthens; the *theorem* bound (ε·N with
  live N — dashed) stays low because it loosens as fast as N grows.
* **Right panel** — mean overestimation error vs amplification factor,
  showing the raw error the amplified heavy hitters push onto colliding
  light flows.

The picture makes the honest finding legible: volumetric amplification
on real traffic breaks the *sized-for-baseline* promise, not the
self-scaling textbook bound.
"""

from __future__ import annotations

import csv
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # headless — no GUI required
import matplotlib.pyplot as plt

from sketchflow.real_adversary import (
    real_adversarial_study,
    write_real_adversarial_csv,
)

__all__ = ["load_real_adversarial_csv", "plot_real_adversarial", "build_rows"]

# One colour per trace; provisioning level distinguishes the marker/dash.
TRACE_COLOUR: dict[str, str] = {"MAWI": "#d62728", "CIC-IDS": "#1f77b4"}
# Two representative provisioning levels: sized (generous) vs under-provisioned.
PROV_STYLE = {
    "sized": {"marker": "o", "linestyle": "-"},       # small ε, wide sketch
    "under": {"marker": "x", "linestyle": "--"},      # large ε, narrow sketch
}


def _prov_label(epsilon: float) -> str:
    """Bucket an ε into a coarse provisioning label for the legend."""
    return "sized" if epsilon <= 0.02 else "under"


def load_real_adversarial_csv(csv_path: Path) -> dict[tuple[str, float], list[dict]]:
    """Load the study CSV, grouped by (trace, ε), rows sorted by factor."""
    by_series: dict[tuple[str, float], list[dict]] = {}
    with open(csv_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            parsed = {
                "factor": int(row["factor"]),
                "epsilon": float(row["epsilon"]),
                "width": int(row["width"]),
                "mean_error": float(row["mean_error"]),
                "violation_rate_theorem": float(row["violation_rate_theorem"]),
                "violation_rate_provisioned": float(
                    row["violation_rate_provisioned"]
                ),
            }
            by_series.setdefault((row["trace"], parsed["epsilon"]), []).append(parsed)
    for key in by_series:
        by_series[key].sort(key=lambda r: r["factor"])
    return by_series


def plot_real_adversarial(
    data: dict[tuple[str, float], list[dict]],
    out_path: Path,
    title: str = "SketchFlow: heavy-hitter amplification on real traces",
) -> Path:
    """Render the two-panel real-trace adversarial figure to ``out_path``."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
    fig.suptitle(title, fontsize=14, fontweight="bold")

    for (trace, eps), rows in sorted(data.items()):
        colour = TRACE_COLOUR.get(trace, "grey")
        prov = _prov_label(eps)
        style = PROV_STYLE.get(prov, {"marker": ".", "linestyle": "-"})
        width = rows[0]["width"]
        tag = "sized" if prov == "sized" else "under-provisioned"
        label = f"{trace} — {tag} (ε={eps:g}, w={width})"
        xs = [r["factor"] for r in rows]

        # Left: the operator's fixed promise ε·N₀ (this is what breaks).
        ax1.plot(
            xs,
            [r["violation_rate_provisioned"] for r in rows],
            label=label,
            color=colour,
            markersize=6,
            **style,
        )
        # Right: mean overestimation error.
        ax2.plot(
            xs,
            [r["mean_error"] for r in rows],
            label=label,
            color=colour,
            markersize=6,
            **style,
        )

    ax1.set_xlabel("Heavy-hitter amplification factor", fontsize=11)
    ax1.set_ylabel("Provisioned-promise violation rate (ε·N₀)", fontsize=11)
    ax1.set_xscale("log")
    ax1.legend(fontsize=8)
    ax1.grid(True, which="both", alpha=0.3)
    ax1.set_title("Fixed baseline promise breaks when under-provisioned", fontsize=11)

    ax2.set_xlabel("Heavy-hitter amplification factor", fontsize=11)
    ax2.set_ylabel("Mean overestimation error", fontsize=11)
    ax2.set_xscale("log")
    ax2.set_yscale("log")
    ax2.legend(fontsize=8)
    ax2.grid(True, which="both", alpha=0.3)
    ax2.set_title("Error pushed onto colliding light flows", fontsize=11)

    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(out_path), dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path


def build_rows() -> list[dict]:
    """Load both real traces and run the amplification study on each.

    Returns the combined list of study rows (MAWI then CIC-IDS). Imports
    the loaders lazily so a missing optional dependency (dpkt) only
    affects this orchestration path, not the pure-logic module.
    """
    from sketchflow.mawi import load_mawi
    from sketchflow.cicids import load_cicids

    mawi_stream = list(load_mawi())
    cic_stream = list(load_cicids())
    rows = real_adversarial_study("MAWI", mawi_stream)
    rows += real_adversarial_study("CIC-IDS", cic_stream)
    return rows


def main(argv: list[str] | None = None) -> None:
    """Regenerate report/real_adversarial.csv + report/real_adversarial.png."""
    import argparse

    parser = argparse.ArgumentParser(
        description="SketchFlow real-trace adversarial plot (step 22)",
    )
    parser.add_argument(
        "--csv", type=str, default="report/real_adversarial.csv",
        help="output/input CSV path (default: report/real_adversarial.csv)",
    )
    parser.add_argument(
        "--out", type=str, default="report/real_adversarial.png",
        help="output PNG path (default: report/real_adversarial.png)",
    )
    args = parser.parse_args(argv)

    print("Loading real traces (MAWI pcap + CIC-IDS flows) …")
    rows = build_rows()
    csv_path = write_real_adversarial_csv(rows, args.csv)
    print(f"Wrote {csv_path} ({len(rows)} rows)")

    data = load_real_adversarial_csv(Path(args.csv))
    out = plot_real_adversarial(data, Path(args.out))
    print(f"Saved {out}")
    for (trace, eps), trows in sorted(data.items()):
        first, last = trows[0], trows[-1]
        print(
            f"{trace} eps={eps:g} (w={trows[0]['width']}): "
            f"provisioned violation "
            f"{first['violation_rate_provisioned']:.4f} (x1) -> "
            f"{last['violation_rate_provisioned']:.4f} (x{last['factor']}); "
            f"theorem max "
            f"{max(r['violation_rate_theorem'] for r in trows):.4f}"
        )


if __name__ == "__main__":
    main()
