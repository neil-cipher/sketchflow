"""Step 22 gate: adversary on real traces (heavy-hitter amplification).

plan.json step 22 gate: "artifact: report/real_adversarial.png; where the
bound holds vs breaks on real data".

The empirical finding under test: a *well-provisioned* CMS shrugs off
volumetric heavy-hitter amplification on real traffic (both the textbook
ε·N bound and the operator's fixed ε·N₀ promise hold); an
*under-provisioned* CMS lets the fixed baseline promise break as the top
flows are amplified. The self-scaling textbook bound (ε·N, N = live
length) never breaks from volume alone, because it loosens as fast as N
grows — captured by the invariant violation_rate_theorem ≤
violation_rate_provisioned on every row.
"""

import csv
from collections import Counter
from pathlib import Path

import pytest

from sketchflow.cms import CountMinSketch, size_cms
from sketchflow.real_adversary import (
    CSV_COLUMNS,
    amplify_stream,
    heavy_hitter_targets,
    measure_amplified,
    real_adversarial_study,
    write_real_adversarial_csv,
)
from sketchflow.real_plot import (
    build_rows,
    load_real_adversarial_csv,
    plot_real_adversarial,
)


# ── a small, deterministic synthetic "trace": a few heavy hitters over
#    a long tail of light flows, so amplification has light keys to bury ──
def _synthetic_trace() -> list[str]:
    stream: list[str] = []
    for h, count in (("heavy-A", 200), ("heavy-B", 150), ("heavy-C", 120)):
        stream.extend([h] * count)
    for i in range(600):          # 600 light flows, one event each
        stream.append(f"light-{i}")
    return stream


# ── heavy_hitter_targets ─────────────────────────────────────────────
def test_targets_are_the_heaviest_keys():
    stream = _synthetic_trace()
    tg = heavy_hitter_targets(stream, 3)
    assert tg == {"heavy-A", "heavy-B", "heavy-C"}


def test_targets_zero_and_oversized():
    stream = _synthetic_trace()
    assert heavy_hitter_targets(stream, 0) == set()
    # asking for more than distinct keys returns all distinct keys
    everything = heavy_hitter_targets(stream, 10_000)
    assert everything == set(stream)


def test_targets_negative_raises():
    with pytest.raises(ValueError):
        heavy_hitter_targets(["a"], -1)


# ── amplify_stream ───────────────────────────────────────────────────
def test_amplify_factor_one_is_identity_multiset():
    stream = _synthetic_trace()
    tg = heavy_hitter_targets(stream, 3)
    assert Counter(amplify_stream(stream, tg, 1)) == Counter(stream)


def test_amplify_multiplies_only_targets():
    stream = _synthetic_trace()
    tg = heavy_hitter_targets(stream, 3)
    before = Counter(stream)
    after = Counter(amplify_stream(stream, tg, 10))
    for key, c in before.items():
        expected = c * 10 if key in tg else c
        assert after[key] == expected
    # total grew by exactly the amplified target mass
    target_mass = sum(before[k] for k in tg)
    assert sum(after.values()) == sum(before.values()) + target_mass * 9


def test_amplify_factor_below_one_raises():
    with pytest.raises(ValueError):
        amplify_stream(["a"], {"a"}, 0)


# ── measure_amplified ────────────────────────────────────────────────
def test_measure_never_undercounts_and_flat_when_roomy():
    # A very wide sketch has no collisions on this small key set:
    # every estimate is exact, so all errors and violation rates are 0.
    stream = _synthetic_trace()
    m = measure_amplified(stream, width=4096, depth=4, seed=0,
                          epsilon=0.01, baseline_n=len(stream))
    assert m["mean_error"] == 0.0
    assert m["violation_rate_theorem"] == 0.0
    assert m["violation_rate_provisioned"] == 0.0
    assert m["n_events"] == len(stream)
    assert m["distinct_keys"] == len(set(stream))


def test_theorem_threshold_never_below_provisioned():
    # ε·N ≥ ε·N₀ whenever N ≥ N₀, so a theorem violation is always also a
    # provisioned violation -> vr_theorem ≤ vr_provisioned, on ANY run.
    stream = _synthetic_trace()
    tg = heavy_hitter_targets(stream, 3)
    amp = amplify_stream(stream, tg, 20)
    width, depth = size_cms(0.1, 0.05)          # deliberately narrow
    m = measure_amplified(amp, width, depth, seed=0,
                          epsilon=0.1, baseline_n=len(stream))
    assert m["violation_rate_theorem"] <= m["violation_rate_provisioned"]


# ── real_adversarial_study: holds-vs-breaks ──────────────────────────
def test_study_row_shape_and_columns():
    stream = _synthetic_trace()
    rows = real_adversarial_study(
        "SYNTH", stream, factors=(1, 5, 20), epsilons=(0.01, 0.1)
    )
    assert len(rows) == 3 * 2
    for r in rows:
        assert set(r.keys()) >= set(CSV_COLUMNS)
        assert r["baseline_n"] == len(stream)     # promise is sized ONCE
        assert r["trace"] == "SYNTH"
        # invariant holds per row
        assert r["violation_rate_theorem"] <= r["violation_rate_provisioned"]


def test_sized_holds_under_provisioned_breaks():
    stream = _synthetic_trace()
    rows = real_adversarial_study(
        "SYNTH", stream, factors=(1, 50), epsilons=(0.01, 0.2)
    )

    def cell(eps, factor):
        return next(r for r in rows if r["epsilon"] == eps and r["factor"] == factor)

    sized_x50 = cell(0.01, 50)
    under_x1 = cell(0.2, 1)
    under_x50 = cell(0.2, 50)

    # A generously-sized sketch is essentially immune to the amplification.
    assert sized_x50["violation_rate_provisioned"] == 0.0
    # Under-provisioning + amplification breaks the fixed baseline promise,
    # and strictly worse than both the sized sketch and its own no-attack case.
    assert under_x50["violation_rate_provisioned"] > under_x1["violation_rate_provisioned"]
    assert under_x50["violation_rate_provisioned"] > sized_x50["violation_rate_provisioned"]
    # Amplification only ever inflates error (heavy hitters bury light flows).
    assert under_x50["mean_error"] >= under_x1["mean_error"]


def test_n_events_grows_with_factor_baseline_fixed():
    stream = _synthetic_trace()
    rows = real_adversarial_study(
        "SYNTH", stream, factors=(1, 10), epsilons=(0.1,)
    )
    r1 = next(r for r in rows if r["factor"] == 1)
    r10 = next(r for r in rows if r["factor"] == 10)
    assert r10["n_events"] > r1["n_events"]
    assert r1["baseline_n"] == r10["baseline_n"] == len(stream)


# ── CSV artifact round-trip ──────────────────────────────────────────
def test_csv_roundtrip(tmp_path):
    stream = _synthetic_trace()
    rows = real_adversarial_study("SYNTH", stream, factors=(1, 5), epsilons=(0.01,))
    path = write_real_adversarial_csv(rows, str(tmp_path / "ra.csv"))
    with open(path) as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == CSV_COLUMNS
        back = list(reader)
    assert len(back) == len(rows)


# ── PNG artifact regeneration (the gate) ─────────────────────────────
def test_plot_regenerates_png(tmp_path):
    stream = _synthetic_trace()
    rows = real_adversarial_study(
        "SYNTH", stream, factors=(1, 5, 20), epsilons=(0.01, 0.1)
    )
    csv_path = write_real_adversarial_csv(rows, str(tmp_path / "ra.csv"))
    data = load_real_adversarial_csv(Path(csv_path))
    out = plot_real_adversarial(data, tmp_path / "ra.png")
    assert out.exists()
    assert out.stat().st_size > 0


def test_committed_png_and_csv_exist():
    # The step-22 gate artifact must be present in the repo.
    root = Path(__file__).resolve().parents[1]
    assert (root / "report" / "real_adversarial.png").exists()
    assert (root / "report" / "real_adversarial.csv").exists()


# ── light integration on a REAL trace (skips if dpkt/data unavailable) ──
def test_real_trace_integration_holds_vs_breaks():
    try:
        from sketchflow.mawi import load_mawi
        stream = list(load_mawi())
    except Exception as exc:  # dpkt missing or sample absent
        pytest.skip(f"MAWI sample unavailable: {exc}")

    rows = real_adversarial_study(
        "MAWI", stream, factors=(1, 20), epsilons=(0.01, 0.1)
    )

    def cell(eps, factor):
        return next(r for r in rows if r["epsilon"] == eps and r["factor"] == factor)

    # sized sketch holds; under-provisioned breaks under amplification
    assert cell(0.01, 20)["violation_rate_provisioned"] <= 0.001
    assert (
        cell(0.1, 20)["violation_rate_provisioned"]
        > cell(0.1, 1)["violation_rate_provisioned"]
    )


def test_build_rows_smoke():
    # build_rows loads both real traces; skip cleanly if deps/data missing.
    try:
        rows = build_rows()
    except Exception as exc:
        pytest.skip(f"real traces unavailable: {exc}")
    traces = {r["trace"] for r in rows}
    assert {"MAWI", "CIC-IDS"} <= traces
