"""Guarantee-violation meter (Phase P5, step 20).

Step 6 first checked the CMS's core promise:

    query(key) - true(key) <= eps * N     with probability >= 1 - delta

by fixing a benign stream and varying the hash seed across 300 trials,
then counting how often a handful of heavy-hitter keys broke the bound.
That was a one-off test. Step 19 then showed that a known-seed attacker
can choose a stream that breaks the same bound far more often than any
benign stream would -- but never actually *measured* the violation rate
on that adversarial stream using the same yardstick as the benign check.

This module turns "check the bound" into a reusable meter with two call
sites:

1. ``benign_violation_study`` -- re-run the step-6 style check as a
   general-purpose utility: does the empirical violation rate stay
   <= delta (up to sampling margin) on an ordinary, non-adversarial
   stream? This is the promise's home turf.
2. ``adversarial_violation_study`` -- apply the SAME meter to a stream
   built by ``sketchflow.adversary`` (a known-seed collision attack).
   There is no claim the bound *should* hold here (the attacker breaks
   the theorem's own randomness assumption -- see adversary.py's
   docstring) -- the point is to quantify by how much it fails, using
   an apples-to-apples measurement against the benign case.

Reference: Cormode & Muthukrishnan, "An improved data stream summary:
the count-min sketch and its applications", J. Algorithms 55 (2005),
Theorem 1 (the eps/delta guarantee this module measures).
"""

from __future__ import annotations

from collections import Counter

from sketchflow.cms import CountMinSketch, size_cms
from sketchflow.streams import zipfian_stream

__all__ = [
    "violating_keys",
    "violation_rate",
    "benign_violation_study",
    "adversarial_violation_study",
]


def violating_keys(
    sketch: CountMinSketch, true_counts: dict, epsilon: float
) -> list[str]:
    """Keys in ``true_counts`` whose CMS estimate breaks the eps*N bound.

    N is ``sketch.total`` -- the same stream-length term the eps/delta
    theorem uses. A key is a "violation" if:

        sketch.query(key) - true_counts[key] > epsilon * sketch.total

    Returns the empty list if every key satisfied the promise.
    """
    threshold = epsilon * sketch.total
    return [
        key
        for key, true in true_counts.items()
        if sketch.query(key) - true > threshold
    ]


def violation_rate(
    sketch: CountMinSketch, true_counts: dict, epsilon: float
) -> float:
    """Fraction of ``true_counts`` keys that violate the eps*N bound.

    0.0 means the bound held for every key measured; 1.0 means it broke
    for all of them. This is the empirical stand-in for the theorem's
    delta -- for a single fixed key, delta is P(violation) over the
    hash-seed randomness; here we report the observed rate over
    whatever set of (key, trial) pairs the caller measured.
    """
    if not true_counts:
        return 0.0
    return len(violating_keys(sketch, true_counts, epsilon)) / len(true_counts)


def benign_violation_study(
    epsilon: float = 0.01,
    delta: float = 0.05,
    num_trials: int = 300,
    n_items: int = 10_000,
    universe: int = 1_000,
    alpha: float = 1.2,
    stream_seed: int = 42,
    num_target_keys: int = 10,
) -> dict[str, float]:
    """Empirically measure P(error > eps*N) on a BENIGN (non-adversarial)
    stream, the way step 6 first checked it.

    The theorem's promise is PER-KEY, over the randomness of the hash
    seed for a FIXED stream: for one query key, P(violation) <= delta.
    Method: fix one Zipfian stream (``stream_seed``), build ``num_trials``
    independent CMS sketches (each sized via ``size_cms(epsilon, delta)``,
    each with a different hash seed 0..num_trials-1), and for each of the
    stream's ``num_target_keys`` heaviest keys, count across trials how
    often the bound broke.

    Returns ``{key: empirical_violation_rate}`` -- one rate per target
    key, each expected to be <= delta (up to sampling margin; see the
    step-20 gate test for the margin used).
    """
    width, depth = size_cms(epsilon, delta)
    stream = list(
        zipfian_stream(n_items=n_items, universe=universe, alpha=alpha, seed=stream_seed)
    )
    true_counts = Counter(stream)
    target_keys = [k for k, _ in true_counts.most_common(num_target_keys)]

    violations = {k: 0 for k in target_keys}
    for trial_seed in range(num_trials):
        sketch = CountMinSketch(width=width, depth=depth, seed=trial_seed)
        for item in stream:
            sketch.add(item)
        threshold = epsilon * sketch.total
        for k in target_keys:
            if sketch.query(k) - true_counts[k] > threshold:
                violations[k] += 1

    return {k: v / num_trials for k, v in violations.items()}


def adversarial_violation_study(
    sketch: CountMinSketch, true_counts: dict, epsilon: float
) -> float:
    """Quantify the violation rate on an adversarial (collision-maximising)
    stream, using the exact same meter as the benign study.

    Unlike ``benign_violation_study``, this makes no claim that the rate
    should stay <= delta -- a known-seed attacker (see
    ``sketchflow.adversary``) chooses the stream itself, which breaks the
    theorem's own randomness assumption. The point of this function is
    only to report the number on the same scale as the benign case, so
    the two can be compared directly (plan.json step 20's gate: "on
    adversarial streams it is quantified").
    """
    return violation_rate(sketch, true_counts, epsilon)
