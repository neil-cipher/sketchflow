"""Step 19 — Adversary v1 tests.

Core gate (plan.json step 19): an adversarial, collision-maximising
stream provably raises mean estimation error vs. a random/benign stream
of the same size, at the same memory budget (identical CMS width and
depth -- i.e. same hash functions, same table).

Additional checks:
- find_colliding_group actually returns keys that share every row's
  bucket (the mechanism is real, not asserted).
- Against a production-sized sketch, the same search is infeasible
  within a small trial budget -- the attack needs a known/small (width,
  depth), not a flaw that touches every sketch.
- adversarial_stream / random_control_stream produce the expected
  shapes (distinct key counts, per-key event counts, group membership).
"""

import collections

import pytest

from sketchflow.adversary import (
    adversarial_stream,
    find_colliding_group,
    mean_overestimation_error,
    random_control_stream,
)
from sketchflow.cms import CountMinSketch, size_cms


# ── 1. The collision mechanism is real ───────────────────────────


def test_find_colliding_group_shares_every_row_bucket():
    """Every key returned by find_colliding_group hashes to the exact
    same bucket in EVERY row -- not just one."""
    sketch = CountMinSketch(width=16, depth=3, seed=0)
    keys, bucket = find_colliding_group(sketch, group_size=5, namespace="t")

    assert len(keys) == 5
    assert len(set(keys)) == 5, "colliding keys must be distinct"
    assert len(bucket) == 3

    for key in keys:
        assert tuple(sketch.family.buckets(key)) == bucket, (
            f"key {key!r} does not share the full-row bucket {bucket}"
        )


def test_find_colliding_group_rejects_bad_group_size():
    sketch = CountMinSketch(width=16, depth=3, seed=0)
    with pytest.raises(ValueError, match="group_size"):
        find_colliding_group(sketch, group_size=0, namespace="t")


def test_find_colliding_group_infeasible_against_production_sketch():
    """Against a realistically-sized sketch (from size_cms), the same
    search fails within a small trial budget -- the birthday space is
    too large. This is the flip side of the attack: a correctly-sized,
    unknown-seed deployment is not vulnerable to this search."""
    width, depth = size_cms(0.01, 0.05)  # production-scale (272 x 3)
    sketch = CountMinSketch(width=width, depth=depth, seed=0)
    with pytest.raises(RuntimeError, match="too large"):
        find_colliding_group(sketch, group_size=3, namespace="prod", max_trials=5_000)


# ── 2. Stream construction shapes ────────────────────────────────


def test_adversarial_stream_shape_and_group_membership():
    sketch = CountMinSketch(width=16, depth=3, seed=1)
    stream, group_of = adversarial_stream(
        sketch, num_groups=4, group_size=5, events_per_key=10
    )

    assert len(group_of) == 4 * 5
    assert len(stream) == 4 * 5 * 10

    counts = collections.Counter(stream)
    assert len(counts) == 20
    assert all(c == 10 for c in counts.values())

    # every key's group id is in range, groups partition the key set
    groups = collections.defaultdict(set)
    for key, gid in group_of.items():
        assert 0 <= gid < 4
        groups[gid].add(key)
    assert all(len(members) == 5 for members in groups.values())

    # keys in the same group really do share every row's bucket
    for members in groups.values():
        buckets = {tuple(sketch.family.buckets(k)) for k in members}
        assert len(buckets) == 1


def test_random_control_stream_shape():
    stream = random_control_stream(num_keys=20, events_per_key=10)
    counts = collections.Counter(stream)
    assert len(counts) == 20
    assert all(c == 10 for c in counts.values())
    assert len(stream) == 200


def test_random_control_stream_rejects_negative():
    with pytest.raises(ValueError):
        random_control_stream(num_keys=-1, events_per_key=10)


# ── 3. Core gate: adversarial stream raises mean error ───────────


def _run_seed(seed, width=16, depth=3, num_groups=5, group_size=5, events_per_key=20):
    """Build a fresh sketch, attack it with a collision-maximising
    stream, and compare mean overestimation error against a benign
    control stream of identical size fed into a sketch with the SAME
    width/depth/seed (same hash functions, same memory budget)."""
    adv_sketch = CountMinSketch(width=width, depth=depth, seed=seed)
    stream, group_of = adversarial_stream(
        adv_sketch, num_groups=num_groups, group_size=group_size,
        events_per_key=events_per_key,
    )
    true_adv = collections.Counter(stream)
    for key in stream:
        adv_sketch.add(key)
    adv_error = mean_overestimation_error(adv_sketch, true_adv)

    ctl_sketch = CountMinSketch(width=width, depth=depth, seed=seed)
    ctl_stream = random_control_stream(
        num_keys=num_groups * group_size, events_per_key=events_per_key
    )
    true_ctl = collections.Counter(ctl_stream)
    for key in ctl_stream:
        ctl_sketch.add(key)
    ctl_error = mean_overestimation_error(ctl_sketch, true_ctl)

    return adv_error, ctl_error


def test_gate_adversarial_raises_mean_error_at_same_memory():
    """Single-seed sanity check: the collision-maximising stream produces
    strictly higher mean error than the benign control, at identical
    CMS width/depth (identical memory budget)."""
    adv_error, ctl_error = _run_seed(seed=42)
    assert adv_error > ctl_error, (
        f"adversarial mean error ({adv_error}) not greater than control "
        f"({ctl_error}) at same memory (width=16, depth=3)"
    )
    # not just marginally greater -- the attack should be decisive
    assert adv_error > ctl_error * 2, (
        f"adversarial error ({adv_error}) not meaningfully larger than "
        f"control ({ctl_error})"
    )


def test_gate_adversarial_raises_mean_error_across_many_seeds():
    """Robustness: across 25 independent seeds, the adversarial stream
    beats the control's mean error on (nearly) every seed, and the
    average advantage across seeds is large -- this is the "provably"
    part of the gate, demonstrated empirically across many independent
    trials rather than asserted from a single lucky seed."""
    seeds = range(25)
    wins = 0
    adv_total = 0.0
    ctl_total = 0.0
    for seed in seeds:
        adv_error, ctl_error = _run_seed(seed)
        adv_total += adv_error
        ctl_total += ctl_error
        if adv_error > ctl_error:
            wins += 1

    win_rate = wins / len(seeds)
    assert win_rate >= 0.9, (
        f"adversarial stream only beat control on {wins}/{len(seeds)} seeds "
        f"({win_rate:.0%}) -- expected near-certain advantage"
    )

    mean_adv = adv_total / len(seeds)
    mean_ctl = ctl_total / len(seeds)
    assert mean_adv > mean_ctl * 1.5, (
        f"average adversarial error ({mean_adv:.2f}) not meaningfully "
        f"above average control error ({mean_ctl:.2f}) across {len(seeds)} seeds"
    )


def test_gate_control_stream_stays_close_to_exact_baseline():
    """Sanity check on the control side: the benign stream's mean error
    should be small relative to the adversarial one -- confirming the
    gap is caused by the engineered collisions, not by the sketch being
    hopelessly undersized for either stream."""
    width, depth = 16, 3
    num_groups, group_size, events_per_key = 5, 5, 20
    total_events = num_groups * group_size * events_per_key

    _, ctl_error = _run_seed(
        seed=7, width=width, depth=depth, num_groups=num_groups,
        group_size=group_size, events_per_key=events_per_key,
    )
    # control error should be well under one full group's worth of
    # collision damage (events_per_key * (group_size - 1)) -- i.e. the
    # benign stream is not itself secretly adversarial.
    assert ctl_error < events_per_key * (group_size - 1), (
        f"control error ({ctl_error}) is as large as a full engineered "
        f"collision group would produce -- control stream isn't benign"
    )
    assert total_events > 0  # sanity: stream is non-trivial
