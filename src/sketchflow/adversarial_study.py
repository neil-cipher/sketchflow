"""CU vs plain CMS under adversarial load (Phase P5, step 21).

Step 9 showed Conservative Update (CU) cuts overestimation on ordinary
streams: by only bumping counters at or below the current minimum, CU
avoids piling noise onto cells that are already collision-inflated
(Estan & Varghese, SIGCOMM 2002, Section 4.2). Step 19 built a
known-seed attacker (Crosby & Wallach threat model, USENIX Security
2003) whose "full-row collision groups" defeat the min-estimator's
escape hatch: every group member shares the SAME bucket in EVERY row.
Step 20 built the meter that measures how often the eps/delta promise
(Cormode & Muthukrishnan, J. Algorithms 2005, Theorem 1) breaks.

Step 21 asks the natural next question: does CU's advantage survive the
attack? The honest answer this module measures: NO. Against a pure
full-row collision group CU degenerates into plain CMS. CU's whole
trick depends on some row holding a smaller, cleaner counter it can
trust -- but a full-row collider's bucket counters rise in lock-step in
every row (each add finds min == every one of the group's cells and
bumps them all), so each member's estimate still absorbs the entire
group's traffic. On the size-matched benign control stream, CU keeps
its usual edge. Robustness against this attacker comes from sketch
sizing and a secret, re-randomized seed -- not from conservative
update.

Artifact (plan.json step 21 gate): ``report/adversarial.csv`` --
violation rates + mean errors for {cms, cu} x {adversarial, control}
across seeds, regenerable via::

    PYTHONPATH=src python -m sketchflow.adversarial_study
"""

from __future__ import annotations

import csv
import os
from collections import Counter

from sketchflow.adversary import (
    adversarial_stream,
    mean_overestimation_error,
    random_control_stream,
)
from sketchflow.cms import CountMinSketch
from sketchflow.cu_cms import ConservativeUpdateCMS
from sketchflow.guarantee_meter import violation_rate

__all__ = [
    "measure_stream",
    "adversarial_cu_study",
    "write_adversarial_csv",
    "CSV_COLUMNS",
]

CSV_COLUMNS = [
    "seed",
    "variant",
    "stream",
    "width",
    "depth",
    "epsilon",
    "n_events",
    "distinct_keys",
    "violation_rate",
    "mean_error",
]

_VARIANTS = (("cms", CountMinSketch), ("cu", ConservativeUpdateCMS))


def measure_stream(
    sketch_cls, stream: list[str], width: int, depth: int, seed: int, epsilon: float
) -> dict:
    """Feed ``stream`` into a fresh ``sketch_cls(width, depth, seed)`` and
    measure it with the step-20 meter.

    Returns ``{"violation_rate": ..., "mean_error": ...,
    "n_events": ..., "distinct_keys": ...}``. Both sketch variants share
    the same hash family for identical (width, depth, seed), so a
    collision group found against one applies verbatim to the other --
    that is what makes the CU-vs-CMS comparison apples-to-apples.
    """
    sketch = sketch_cls(width=width, depth=depth, seed=seed)
    for key in stream:
        sketch.add(key)
    true_counts = Counter(stream)
    return {
        "violation_rate": violation_rate(sketch, true_counts, epsilon),
        "mean_error": mean_overestimation_error(sketch, true_counts),
        "n_events": len(stream),
        "distinct_keys": len(true_counts),
    }


def adversarial_cu_study(
    width: int = 16,
    depth: int = 3,
    seeds=range(10),
    num_groups: int = 5,
    group_size: int = 5,
    events_per_key: int = 20,
    epsilon: float = 0.02,
    max_trials: int = 200_000,
) -> list[dict]:
    """Run {cms, cu} x {adversarial, control} for every hash seed.

    For each seed: search collision groups against that seed's hash
    family (the attack is seed-specific), build the step-19 adversarial
    stream and its size-matched benign control, then replay BOTH streams
    into BOTH sketch variants at the identical (width, depth, seed)
    memory budget. Defaults mirror the step-19/20 demo sketch
    (deliberately small so the collision search is tractable -- see
    adversary.py's docstring for why production sizing defeats it).

    Returns one row dict per (seed, variant, stream) combination.
    """
    rows: list[dict] = []
    for seed in seeds:
        probe = CountMinSketch(width=width, depth=depth, seed=seed)
        adv_stream, _groups = adversarial_stream(
            probe, num_groups, group_size, events_per_key, max_trials=max_trials
        )
        ctl_stream = random_control_stream(num_groups * group_size, events_per_key)
        for stream_name, stream in (("adversarial", adv_stream), ("control", ctl_stream)):
            for variant_name, sketch_cls in _VARIANTS:
                m = measure_stream(sketch_cls, stream, width, depth, seed, epsilon)
                rows.append(
                    {
                        "seed": seed,
                        "variant": variant_name,
                        "stream": stream_name,
                        "width": width,
                        "depth": depth,
                        "epsilon": epsilon,
                        **m,
                    }
                )
    return rows


def write_adversarial_csv(rows: list[dict], path: str = "report/adversarial.csv") -> str:
    """Write study rows to ``path`` (creating the directory if needed)."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row[col] for col in CSV_COLUMNS})
    return path


def _mean(rows: list[dict], variant: str, stream: str, field: str) -> float:
    vals = [r[field] for r in rows if r["variant"] == variant and r["stream"] == stream]
    return sum(vals) / len(vals)


def main() -> None:
    rows = adversarial_cu_study()
    path = write_adversarial_csv(rows)
    print(f"wrote {path} ({len(rows)} rows)")
    for stream in ("adversarial", "control"):
        for variant in ("cms", "cu"):
            vr = _mean(rows, variant, stream, "violation_rate")
            me = _mean(rows, variant, stream, "mean_error")
            print(f"{stream:11s} {variant:3s}: violation_rate={vr:.3f} mean_error={me:.2f}")


if __name__ == "__main__":
    main()
