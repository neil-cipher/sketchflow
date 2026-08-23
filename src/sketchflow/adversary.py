"""Adversary v1 — collision-maximising input generator (Phase P5, step 19).

Every prior step measured the Count-Min Sketch under RANDOM keys
(Zipfian synthetic streams, CIC-IDS flows, MAWI backbone traffic). But
the ε/δ guarantee itself is a promise about the sketch's OWN hash
randomness, for any *fixed* stream — it says nothing about what happens
when the stream itself is chosen by someone who already knows which
hash functions the sketch is using.

Threat model (known-seed / white-box attacker — the standard model in
the hash-flooding / algorithmic-complexity-attack literature: Crosby &
Wallach, "Denial of Service via Algorithmic Complexity Attacks", USENIX
Security 2003). Given a CountMinSketch's exact (width, depth, seed) —
e.g. leaked, guessed, or simply fixed across every deployment, a real
operational mistake — an attacker can brute-force search for keys that
hash to the SAME bucket in EVERY row simultaneously. A group of such
"full-row colliders" all pile their counts on top of each other in
every row at once, so the min-estimator (which normally escapes a
collision in one row by trusting another) has nowhere left to hide.

This is an honest, disclosed attack against a *specific, named* threat
model — not a claim that CMS is "broken". A sketch whose hash seed is
kept secret and re-randomized per deployment is NOT vulnerable: finding
a full-row collision against an unknown seed is exactly as hard as the
birthday bound the sizing already assumes (width × depth large enough
that the search space dwarfs anything feasible — see
``find_colliding_group``'s docstring and its own test against a
production-sized sketch). What this module demonstrates empirically is
narrower and provable: IF the seed is known, collision-maximising
traffic reliably raises mean estimation error above an equal-size
benign stream at the *identical* memory budget (same width, depth).
"""
from __future__ import annotations

import random

from sketchflow.cms import CountMinSketch

__all__ = [
    "find_colliding_group",
    "adversarial_stream",
    "random_control_stream",
    "mean_overestimation_error",
]


def find_colliding_group(
    sketch: CountMinSketch,
    group_size: int,
    namespace: str,
    max_trials: int = 200_000,
) -> tuple[list[str], tuple[int, ...]]:
    """Brute-force search for ``group_size`` distinct keys that share the
    exact same bucket-index tuple in EVERY row of ``sketch``'s hash family
    (a "full-row collision group").

    Candidates are drawn deterministically as ``f"{namespace}-{i}"`` for
    i = 0, 1, 2, ... so the search is reproducible given the same sketch
    and namespace. Returns ``(keys, bucket_tuple)``.

    Raises ``RuntimeError`` if no such group turns up within
    ``max_trials``. For a properly-sized production sketch that is the
    EXPECTED outcome — width × depth is large enough that the birthday
    space dwarfs any feasible brute-force search. This function is only
    tractable against a deliberately small (width, depth); that is the
    point of the demonstration, not a flaw in the search.
    """
    if group_size < 1:
        raise ValueError("group_size must be >= 1")
    buckets: dict[tuple[int, ...], list[str]] = {}
    for i in range(max_trials):
        cand = f"{namespace}-{i}"
        b = tuple(sketch.family.buckets(cand))
        group = buckets.setdefault(b, [])
        group.append(cand)
        if len(group) >= group_size:
            return group[:group_size], b
    raise RuntimeError(
        f"no group of {group_size} full-row-colliding keys found in "
        f"{max_trials} trials against a {sketch.width}x{sketch.depth} "
        "sketch -- space too large for this search (use a smaller "
        "width/depth to demonstrate the attack, or take this failure as "
        "evidence the sketch is safely sized against a known-seed "
        "attacker)"
    )


def adversarial_stream(
    sketch: CountMinSketch,
    num_groups: int,
    group_size: int,
    events_per_key: int,
    max_trials: int = 200_000,
) -> tuple[list[str], dict[str, int]]:
    """Build a collision-maximising stream against ``sketch``.

    Finds ``num_groups`` disjoint full-row-collision groups (each of
    ``group_size`` distinct keys), replays every key ``events_per_key``
    times, and shuffles deterministically (seed fixed at 1, so the
    stream order is reproducible). ``sketch`` is only read (via
    ``find_colliding_group``), never mutated, by this call.

    Returns ``(stream, group_of)`` where ``group_of[key]`` is the id of
    the collision group ``key`` belongs to.

    Total distinct keys = ``num_groups * group_size``.
    Total stream length = distinct keys * ``events_per_key``.
    """
    keys_by_group = []
    group_of: dict[str, int] = {}
    for gid in range(num_groups):
        keys, _bucket = find_colliding_group(
            sketch, group_size, namespace=f"g{gid}", max_trials=max_trials
        )
        keys_by_group.append(keys)
        for k in keys:
            group_of[k] = gid

    stream: list[str] = []
    for keys in keys_by_group:
        for k in keys:
            stream.extend([k] * events_per_key)
    random.Random(1).shuffle(stream)
    return stream, group_of


def random_control_stream(
    num_keys: int, events_per_key: int, prefix: str = "ctl"
) -> list[str]:
    """A benign control stream: ``num_keys`` distinct, ordinary keys (NOT
    engineered for collision), each appearing ``events_per_key`` times,
    shuffled the same way as ``adversarial_stream`` (seed 1) so the two
    streams are comparable — same distinct-key count, same total events,
    same shuffle procedure, differing only in whether the keys were
    chosen to collide.
    """
    if num_keys < 0 or events_per_key < 0:
        raise ValueError("num_keys and events_per_key must be >= 0")
    stream: list[str] = []
    for i in range(num_keys):
        stream.extend([f"{prefix}-{i}"] * events_per_key)
    random.Random(1).shuffle(stream)
    return stream


def mean_overestimation_error(sketch: CountMinSketch, true_counts: dict) -> float:
    """Mean (estimate - true) over every key in ``true_counts``, queried
    against ``sketch``. Never negative (CMS never undercounts), so this
    is both the mean overestimation and the mean absolute error."""
    if not true_counts:
        return 0.0
    diffs = [sketch.query(k) - v for k, v in true_counts.items()]
    return sum(diffs) / len(diffs)
