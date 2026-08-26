"""Adversary on real traces — heavy-hitter amplification (Phase P5, step 22).

Steps 19–21 attacked the Count-Min Sketch with a *known-seed* collision
adversary (Crosby & Wallach, USENIX Security 2003): keys engineered to
share the same bucket in every row. That attack is decisive but needs a
small and/or leaked-seed sketch, and it runs on synthetic keys chosen
by the attacker. This step brings the stress-test to the two real
traces the engine already ingests — MAWI backbone pcap (step 18) and
CIC-IDS-2017 flows (step 16) — under a *different, weaker, and far more
realistic* threat model.

Threat model (heavy-hitter amplification): the attacker does NOT know
the hash seed and cannot pick colliding keys. It can only do what a real
flooder does — send *more traffic to flows that are already heavy* (a
volumetric DDoS / traffic-amplification pattern). We model this by
replaying the real trace but multiplying every occurrence of the top-N
heavy hitters by an amplification ``factor``. Nothing about the keys or
the sketch's internals is touched; only the volume on the existing
heaviest flows grows.

The interesting empirical question this step answers — "where does the
textbook bound hold vs break on real data?" — has a genuinely nuanced
answer, and the artifact (``report/real_adversarial.png``) shows both
sides:

* The **textbook ε/δ bound is relative to the live stream length N**
  (Cormode & Muthukrishnan, J. Algorithms 2005, Theorem 1:
  ``error ≤ ε·N``). Because amplification *raises* N, the bound loosens
  as fast as the attack strengthens, so the *theorem-relative* violation
  rate stays low — the theorem is not broken by volume alone.
* But an operator **provisions memory once, for an expected baseline
  N₀**, effectively promising an *absolute* accuracy of ``ε·N₀``. That
  fixed promise is what heavy-hitter amplification breaks: as the top
  flows swell, light flows sharing their buckets absorb the amplified
  mass and sail past ``ε·N₀``. The *provisioned* violation rate climbs
  steeply with the attack.

So the honest finding is not "CMS breaks" but "*which* promise breaks":
the self-scaling textbook bound survives volumetric amplification on
real traces; the operator's fixed, sized-for-baseline promise does not.
Robustness there comes from provisioning for peak (or re-sizing under
load), not from the theorem.
"""

from __future__ import annotations

import csv
import os
from collections import Counter

from sketchflow.cms import CountMinSketch, size_cms

__all__ = [
    "heavy_hitter_targets",
    "amplify_stream",
    "measure_amplified",
    "real_adversarial_study",
    "write_real_adversarial_csv",
    "CSV_COLUMNS",
]

CSV_COLUMNS = [
    "trace",
    "factor",
    "width",
    "depth",
    "epsilon",
    "delta",
    "baseline_n",
    "n_events",
    "distinct_keys",
    "num_targets",
    "mean_error",
    "violation_rate_theorem",
    "violation_rate_provisioned",
]


def heavy_hitter_targets(stream: list[str], num_targets: int) -> set[str]:
    """Return the ``num_targets`` heaviest keys in ``stream`` (by count).

    These are the flows a volumetric attacker would amplify — the ones
    already carrying the most traffic. Ties are broken by ``Counter``'s
    insertion-ordered ``most_common`` (deterministic for a fixed stream).
    """
    if num_targets < 0:
        raise ValueError("num_targets must be >= 0")
    counts = Counter(stream)
    return {k for k, _ in counts.most_common(num_targets)}


def amplify_stream(
    stream: list[str], targets: set[str], factor: int
) -> list[str]:
    """Replay ``stream`` with every occurrence of a ``targets`` key
    multiplied by ``factor``.

    ``factor == 1`` returns an equivalent stream (each target event kept
    once); ``factor == k`` turns each target event into ``k`` events, so
    a heavy hitter's count grows ``k``-fold while every non-target key is
    left exactly as it was. Order is preserved (irrelevant to the CMS's
    final counters, but keeps the model faithful to a replay).
    """
    if factor < 1:
        raise ValueError("factor must be >= 1")
    out: list[str] = []
    for key in stream:
        out.append(key)
        if factor > 1 and key in targets:
            out.extend([key] * (factor - 1))
    return out


def measure_amplified(
    stream: list[str],
    width: int,
    depth: int,
    seed: int,
    epsilon: float,
    baseline_n: int,
) -> dict:
    """Feed ``stream`` into a fresh ``CountMinSketch`` and measure it under
    two thresholds.

    * ``violation_rate_theorem`` counts keys whose overestimate exceeds
      ``epsilon * N`` with N = the *current* stream length (the textbook
      bound, which scales with the amplified traffic).
    * ``violation_rate_provisioned`` counts keys whose overestimate
      exceeds ``epsilon * baseline_n`` — the *fixed* absolute error an
      operator who sized for ``baseline_n`` was promised.

    Also returns ``mean_error`` (mean overestimate over all keys),
    ``n_events`` and ``distinct_keys``.
    """
    sketch = CountMinSketch(width=width, depth=depth, seed=seed)
    for key in stream:
        sketch.add(key)
    true_counts = Counter(stream)
    n_events = sketch.total
    theorem_thresh = epsilon * n_events
    provisioned_thresh = epsilon * baseline_n

    over = 0.0
    viol_theorem = 0
    viol_prov = 0
    for key, true in true_counts.items():
        diff = sketch.query(key) - true  # >= 0, CMS never undercounts
        over += diff
        if diff > theorem_thresh:
            viol_theorem += 1
        if diff > provisioned_thresh:
            viol_prov += 1
    n_keys = len(true_counts)
    return {
        "n_events": n_events,
        "distinct_keys": n_keys,
        "mean_error": over / n_keys if n_keys else 0.0,
        "violation_rate_theorem": viol_theorem / n_keys if n_keys else 0.0,
        "violation_rate_provisioned": viol_prov / n_keys if n_keys else 0.0,
    }


def real_adversarial_study(
    trace: str,
    stream: list[str],
    factors=(1, 2, 5, 10, 20, 50),
    epsilons=(0.01, 0.1),
    num_targets: int = 10,
    delta: float = 0.05,
    seed: int = 0,
) -> list[dict]:
    """Sweep heavy-hitter amplification × provisioning level on one trace.

    For each ε in ``epsilons`` the operator sizes a CMS ONCE via
    ``size_cms(ε, delta)`` — provisioning for the trace's baseline length
    ``N₀ = len(stream)`` — and the same geometry is replayed at every
    amplification ``factor``. Small ε ⇒ generous width (well provisioned);
    large ε ⇒ narrow width (under provisioned). The top ``num_targets``
    heavy hitters are the amplification targets, shared across all runs so
    the sweeps are directly comparable.

    Each provisioning level is judged against its OWN promise ``ε·N₀``
    (``violation_rate_provisioned``) and against the self-scaling textbook
    bound ``ε·N`` (``violation_rate_theorem``). Returns one row per
    (ε, factor) combination (see ``CSV_COLUMNS``).
    """
    baseline_n = len(stream)
    targets = heavy_hitter_targets(stream, num_targets)

    rows: list[dict] = []
    for epsilon in epsilons:
        width, depth = size_cms(epsilon, delta)
        for factor in factors:
            amp = amplify_stream(stream, targets, factor)
            m = measure_amplified(amp, width, depth, seed, epsilon, baseline_n)
            rows.append(
                {
                    "trace": trace,
                    "factor": factor,
                    "width": width,
                    "depth": depth,
                    "epsilon": epsilon,
                    "delta": delta,
                    "baseline_n": baseline_n,
                    "num_targets": len(targets),
                    **m,
                }
            )
    return rows


def write_real_adversarial_csv(
    rows: list[dict], path: str = "report/real_adversarial.csv"
) -> str:
    """Write study rows to ``path`` (creating the directory if needed)."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row[col] for col in CSV_COLUMNS})
    return path
