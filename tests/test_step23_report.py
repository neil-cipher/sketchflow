"""Step 23 gate: report/EMPIRICAL_STUDY.md — present, every claim cited,
regenerable figures referenced, and headline numbers consistent with the
committed CSV artifacts (the report may not drift from the data)."""

import csv
import re
import statistics
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
REPORT = ROOT / "report" / "EMPIRICAL_STUDY.md"


@pytest.fixture(scope="module")
def text():
    assert REPORT.exists(), "report/EMPIRICAL_STUDY.md must be committed"
    return REPORT.read_text(encoding="utf-8")


def test_report_present_and_substantial(text):
    assert len(text) > 5000, "report should be a real write-up, not a stub"


def test_required_sections(text):
    for heading in [
        "## 1. Method",
        "accuracy vs memory",
        "## 6. Honest limits",
        "## 7. Reproducing everything",
        "## References",
    ]:
        assert heading in text, f"missing section: {heading}"


def test_no_novelty_or_patent_claims(text):
    lowered = text.lower()
    assert "no algorithmic novelty" in lowered
    assert "not a whitepaper" in lowered


def test_every_citation_key_is_defined(text):
    used = set(re.findall(r"\[([A-Z]+\d+|MAWI|CIC\d+)\]", text))
    refs_section = text.split("## References")[1]
    defined = set(re.findall(r"\*\*\[([^\]]+)\]\*\*", refs_section))
    assert used, "report must actually cite sources"
    missing = used - defined
    assert not missing, f"cited but never defined in References: {missing}"


def test_core_claims_carry_citations(text):
    # Each core factual/technical claim area must have at least one citation.
    for key, why in [
        ("[CM05]", "CMS bound / sizing"),
        ("[EV02]", "conservative update"),
        ("[MAE05]", "Space-Saving"),
        ("[CW03]", "hash-flooding threat model"),
        ("[MAWI]", "real trace 1"),
        ("[CIC17]", "real trace 2"),
    ]:
        assert key in text, f"missing citation for {why}"


def test_referenced_artifacts_exist(text):
    for rel in re.findall(r"report/[\w.]+\.(?:csv|png)", text):
        assert (ROOT / rel).exists(), f"report references missing artifact {rel}"
    for rel in re.findall(r"data/[\w.]+\.(?:csv|pcap)", text):
        assert (ROOT / rel).exists(), f"report references missing dataset {rel}"


def test_regeneration_commands_present(text):
    for cmd in [
        "python -m sketchflow.plot",
        "python -m sketchflow.adversarial_study",
        "python -m sketchflow.real_plot",
        "python -m pytest",
    ]:
        assert cmd in text, f"missing regeneration command: {cmd}"


def test_numbers_match_adversarial_csv(text):
    rows = list(csv.DictReader(open(ROOT / "report" / "adversarial.csv")))

    def mean(variant, stream, field):
        vals = [
            float(r[field])
            for r in rows
            if r["variant"] == variant and r["stream"] == stream
        ]
        return statistics.mean(vals)

    # Report claims: both variants fully violated under attack; CU keeps
    # its benign edge on the control.
    assert mean("cms", "adversarial", "violation_rate") == 1.0
    assert mean("cu", "adversarial", "violation_rate") == 1.0
    assert abs(mean("cms", "control", "violation_rate") - 0.464) < 1e-9
    assert mean("cu", "control", "violation_rate") == 0.0
    assert abs(mean("cu", "adversarial", "mean_error") - 80.04) < 0.5


def test_numbers_match_real_adversarial_csv(text):
    rows = list(csv.DictReader(open(ROOT / "report" / "real_adversarial.csv")))
    x50 = {(r["trace"], r["width"]): r for r in rows if r["factor"] == "50"}

    # Well-sized sketches essentially immune at x50 (report Section 5).
    assert float(x50[("MAWI", "272")]["mean_error"]) < 25
    assert float(x50[("CIC-IDS", "272")]["mean_error"]) < 4
    # Under-provisioned breaks the fixed promise: ~3.4% / ~2.4%.
    assert abs(float(x50[("MAWI", "28")]["violation_rate_provisioned"]) - 0.0338) < 0.001
    assert abs(float(x50[("CIC-IDS", "28")]["violation_rate_provisioned"]) - 0.0241) < 0.001
    # Theorem bound holds everywhere (max 0.0009 across all cells).
    max_theo = max(float(r["violation_rate_theorem"]) for r in rows)
    assert max_theo <= 0.001
    # Per-row invariant restated in the report.
    for r in rows:
        assert float(r["violation_rate_theorem"]) <= float(
            r["violation_rate_provisioned"]
        ) + 1e-12


def test_numbers_match_sweep_csv(text):
    rows = list(csv.DictReader(open(ROOT / "report" / "sweep.csv")))
    at = {(r["variant"], r["epsilon"]): r for r in rows}
    # CU roughly halves mean error at eps=0.1 (581.1 -> 331.4).
    assert abs(float(at[("CMS", "0.1")]["mean_abs_error"]) - 581.06) < 0.5
    assert abs(float(at[("CU-CMS", "0.1")]["mean_abs_error"]) - 331.43) < 0.5
    # Honest memory finding: ratio > 1 at eps=0.001, > 2 at eps=0.0005.
    assert float(at[("CMS", "0.001")]["memory_ratio"]) > 1.0
    assert float(at[("CMS", "0.0005")]["memory_ratio"]) > 2.0
