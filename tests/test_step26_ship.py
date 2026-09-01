"""Step 26 — the shipping checkpoint: FINAL INVARIANT SWEEP + release meta.

Two jobs, both required for the `green-sketchflow-final` tag:

1. FINAL INVARIANT SWEEP (``TestFinalInvariantSweep``) — one place that
   re-exercises every core promise the whole project rests on, end to
   end, against the code at HEAD. Individual step tests each guard one
   layer; this sweep proves the layers still cohere *together* at the
   checkpoint. It imports only modules that exist at HEAD (Rule 7).

2. SHIP META (``TestShipArtifacts``) — the "done means verifiable"
   deliverables: a coverage floor in .coveragerc, a static secret-free
   coverage badge whose number matches its data file and clears the
   floor, CI wired to enforce that same floor, a `make coverage` target,
   and a README that surfaces the badge. The floor lives in exactly one
   place (.coveragerc) so the badge, this test, and CI cannot disagree.
"""

import collections
import configparser
import json
import os
import re

import pytest

from sketchflow import covbadge
from sketchflow.adversary import (
    adversarial_stream,
    find_colliding_group,
    mean_overestimation_error,
    random_control_stream,
)
from sketchflow.cms import CountMinSketch, size_cms
from sketchflow.cu_cms import ConservativeUpdateCMS
from sketchflow.engine import SketchEngine
from sketchflow.guarantee_meter import benign_violation_study
from sketchflow.space_saving import SpaceSaving
from sketchflow.streams import zipfian_stream

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _stream(n_items=5000, universe=500, alpha=1.2, seed=7):
    return list(
        zipfian_stream(n_items=n_items, universe=universe, alpha=alpha, seed=seed)
    )


# ─────────────────────────── 1. FINAL INVARIANT SWEEP ───────────────────────────


class TestFinalInvariantSweep:
    def test_cms_never_undercounts(self):
        """Every row cell — and therefore the min-query — is >= the true
        count, for every key on a heavy-tailed stream (the invariant the
        whole sketch is built on)."""
        w, d = size_cms(0.01, 0.05)
        cms = CountMinSketch(width=w, depth=d, seed=1)
        stream = _stream()
        true = collections.Counter(stream)
        for k in stream:
            cms.add(k)
        for key, tc in true.items():
            assert cms.query(key) >= tc
            assert min(cms.row_values(key)) >= tc

    def test_epsilon_delta_promise_holds_on_benign_stream(self):
        """Sizing + CMS + meter together: on a benign stream the measured
        per-key violation rate stays inside the delta promise (with the
        step-20 sampling margin of 3*delta)."""
        delta = 0.05
        rates = benign_violation_study(
            epsilon=0.01, delta=delta, num_trials=60, n_items=5000,
            universe=1000, num_target_keys=10,
        )
        assert rates, "study returned no target keys"
        for key, rate in rates.items():
            assert rate <= 3 * delta, f"{key}: violation rate {rate} > {3*delta}"

    def test_conservative_update_bounded_by_plain_and_never_undercounts(self):
        """CU estimate <= plain-CMS estimate for every key, yet still
        >= the true count — the step-9 promise, re-proven at the
        checkpoint."""
        w, d = size_cms(0.02, 0.05)
        stream = _stream()
        true = collections.Counter(stream)
        plain = CountMinSketch(width=w, depth=d, seed=3)
        cu = ConservativeUpdateCMS(width=w, depth=d, seed=3)
        for k in stream:
            plain.add(k)
            cu.add(k)
        for key, tc in true.items():
            assert cu.query(key) >= tc              # never undercounts
            assert cu.query(key) <= plain.query(key)  # CU tightens

    def test_serialize_roundtrip_preserves_every_estimate(self):
        """Binary round-trip is lossless and the blob is the documented
        24-byte header + depth*width 8-byte counters."""
        w, d = size_cms(0.05, 0.1)
        cms = CountMinSketch(width=w, depth=d, seed=5)
        stream = _stream()
        for k in stream:
            cms.add(k)
        blob = cms.to_bytes()
        assert len(blob) == 24 + d * w * 8
        restored = CountMinSketch.from_bytes(blob)
        for key in set(stream):
            assert restored.query(key) == cms.query(key)

    def test_inner_product_never_undercounts_self_join(self):
        """The self inner-product estimate is >= the true L2^2 of the
        frequency vector (linear-sketch composition, never undercounts)."""
        w, d = size_cms(0.01, 0.05)
        cms = CountMinSketch(width=w, depth=d, seed=9)
        stream = _stream()
        true = collections.Counter(stream)
        for k in stream:
            cms.add(k)
        true_l2_sq = sum(v * v for v in true.values())
        assert cms.inner_product(cms) >= true_l2_sq

    def test_space_saving_guarantees_the_heavy_hitters(self):
        """Every key whose true count exceeds the N/k threshold is
        guaranteed present in the monitored set, and its Space-Saving
        estimate never undercounts (the Space-Saving guarantee)."""
        k = 50
        stream = _stream(n_items=6000, universe=800, seed=11)
        true = collections.Counter(stream)
        n = len(stream)
        ss = SpaceSaving(k=k)
        for key in stream:
            ss.add(key)
        monitored = {key for key, _ in ss.top_k()}
        threshold = n / k
        guaranteed = [key for key, c in true.items() if c > threshold]
        assert guaranteed, "test stream produced no keys above N/k"
        for key in guaranteed:
            assert key in monitored, f"heavy hitter {key} not monitored"
            assert ss.query(key) >= true[key]

    def test_engine_end_to_end_surfaces_true_heavy_hitters(self):
        """The composed CMS + Space-Saving engine surfaces the exact
        top-10 (allowing a little ranking slack) with overestimating CMS
        counts."""
        stream = _stream(n_items=8000, universe=500, seed=2)
        true = collections.Counter(stream)
        eng = SketchEngine(epsilon=0.01, delta=0.05, top_k=50, seed=1)
        for key in stream:
            eng.add(key)
        exact_top10 = {key for key, _ in true.most_common(10)}
        engine_keys = {key for key, _ in eng.heavy_hitters(15)}
        assert exact_top10 <= engine_keys, "engine missed a true top-10 key"
        for key, est in eng.heavy_hitters(15):
            assert est >= true[key], f"{key}: estimate {est} < true {true[key]}"

    def test_known_seed_adversary_beats_benign_control(self):
        """The standout finding, re-proven: at identical memory a
        collision-maximising stream produces strictly higher mean error
        than a size-matched benign control (step-19 parameters)."""
        w, d, ng, gs, epk, seed = 16, 3, 5, 5, 20, 42
        adv = CountMinSketch(width=w, depth=d, seed=seed)
        stream, _ = adversarial_stream(adv, num_groups=ng, group_size=gs,
                                       events_per_key=epk)
        true_adv = collections.Counter(stream)
        for key in stream:
            adv.add(key)
        adv_err = mean_overestimation_error(adv, true_adv)

        ctl = CountMinSketch(width=w, depth=d, seed=seed)
        ctl_stream = random_control_stream(num_keys=ng * gs, events_per_key=epk)
        true_ctl = collections.Counter(ctl_stream)
        for key in ctl_stream:
            ctl.add(key)
        ctl_err = mean_overestimation_error(ctl, true_ctl)

        assert adv_err > ctl_err, (adv_err, ctl_err)

    def test_correctly_sized_sketch_resists_the_search(self):
        """The flip side: against a production-sized sketch the same
        collision search is infeasible in a small budget — robustness
        comes from sizing + a secret seed, not from luck."""
        w, d = size_cms(0.01, 0.05)  # 272 x 3
        sketch = CountMinSketch(width=w, depth=d, seed=0)
        with pytest.raises(RuntimeError, match="too large"):
            find_colliding_group(sketch, group_size=3, namespace="prod",
                                 max_trials=5_000)


# ─────────────────────────── 2. SHIP META ARTIFACTS ───────────────────────────


def _floor():
    parser = configparser.ConfigParser()
    parser.read(os.path.join(_REPO, ".coveragerc"))
    return int(round(float(parser.get("report", "fail_under"))))


class TestShipArtifacts:
    def test_coveragerc_defines_a_sane_floor(self):
        floor = _floor()
        assert 1 <= floor <= 100
        # covbadge reads the identical file — one source of truth
        assert covbadge.read_floor() == floor

    def test_badge_matches_its_data_file_and_clears_the_floor(self):
        floor = _floor()
        svg_path = os.path.join(_REPO, "report", "coverage.svg")
        summary_path = os.path.join(_REPO, "report", "coverage_summary.json")
        assert os.path.exists(svg_path), "coverage badge SVG missing"
        assert os.path.exists(summary_path), "coverage summary missing"

        svg = open(svg_path, encoding="utf-8").read()
        m = re.search(r"coverage:\s*(\d+)%", svg)
        assert m, "could not read a percentage out of the badge"
        badge_pct = int(m.group(1))

        summary = json.load(open(summary_path, encoding="utf-8"))
        assert badge_pct == summary["line_coverage_percent"], "badge != data file"
        assert summary["floor"] == floor, "summary floor != .coveragerc floor"
        assert floor <= badge_pct <= 100, f"badge {badge_pct}% below floor {floor}%"

    def test_badge_renderer_is_deterministic_and_reads_floor(self):
        floor = _floor()
        svg = covbadge.render_svg(covbadge.read_floor(), floor)
        assert svg.startswith("<svg")
        assert f"{floor}%" in svg

    def test_ci_enforces_the_same_floor(self):
        floor = _floor()
        ci = open(os.path.join(_REPO, ".github", "workflows", "ci.yml"),
                  encoding="utf-8").read()
        assert "coverage run" in ci, "CI never runs coverage"
        assert "--fail-under" in ci, "CI does not enforce a coverage floor"
        assert str(floor) in ci, "CI floor number missing / differs from .coveragerc"

    def test_makefile_has_coverage_target(self):
        mk = open(os.path.join(_REPO, "Makefile"), encoding="utf-8").read()
        assert re.search(r"^coverage:", mk, re.M), "no `coverage` make target"
        assert "covbadge" in mk, "coverage target does not regenerate the badge"

    def test_readme_surfaces_the_coverage_badge(self):
        readme = open(os.path.join(_REPO, "README.md"), encoding="utf-8").read()
        assert "coverage.svg" in readme, "README does not show the coverage badge"
        assert "make coverage" in readme, "README does not document `make coverage`"
