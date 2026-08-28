"""Step 24 gate: one-command reproducibility -- `make reproduce` regenerates
every CSV and figure in report/ from seeds, and a CI job proves it works
clean from scratch (make clean -> make reproduce -> full pytest re-validation
of the regenerated data)."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAKEFILE = (ROOT / "Makefile").read_text(encoding="utf-8").replace("\r\n", "\n")
CI = (
    (ROOT / ".github" / "workflows" / "ci.yml")
    .read_text(encoding="utf-8")
    .replace("\r\n", "\n")
)

# Every module whose __main__ writes a report/ artifact, in dependency order.
REPRODUCE_MODULES = [
    "sketchflow.bench",             # -> report/results.csv
    "sketchflow.sweep",             # -> report/sweep.csv
    "sketchflow.plot",              # sweep.csv -> report/accuracy_vs_memory.png
    "sketchflow.adversarial_study", # -> report/adversarial.csv
    "sketchflow.real_plot",         # -> report/real_adversarial.{csv,png}
]

# Every generated artifact the report relies on.
ARTIFACTS = [
    "results.csv",
    "sweep.csv",
    "accuracy_vs_memory.png",
    "adversarial.csv",
    "real_adversarial.csv",
    "real_adversarial.png",
]


def _target_block(name):
    m = re.search(rf"^{name}:[^\n]*\n((?:\t[^\n]*\n?)+)", MAKEFILE, re.M)
    assert m, f"Makefile must define a `{name}` target"
    return m.group(1)


def test_reproduce_target_covers_every_generator():
    block = _target_block("reproduce")
    for mod in REPRODUCE_MODULES:
        assert f"-m {mod}" in block, f"reproduce must run `python -m {mod}`"


def test_reproduce_orders_generators_before_plotters():
    block = _target_block("reproduce")
    # plot.py reads sweep.csv, so sweep must run first.
    assert block.index("sketchflow.sweep") < block.index("sketchflow.plot")


def test_reproduce_sets_pythonpath():
    # The regeneration commands must be runnable from a bare checkout.
    assert "PYTHONPATH=src" in MAKEFILE


def test_clean_target_removes_generated_artifacts():
    block = _target_block("clean")
    assert "report/*.csv" in block and "report/*.png" in block


def test_every_generated_artifact_is_committed_and_nonempty():
    for name in ARTIFACTS:
        p = ROOT / "report" / name
        assert p.exists(), f"report/{name} missing"
        assert p.stat().st_size > 0, f"report/{name} empty"


def test_ci_has_clean_from_scratch_reproduce_job():
    assert re.search(r"^  reproduce:", CI, re.M), "ci.yml needs a reproduce job"
    assert "make clean" in CI, "reproduce job must wipe artifacts first"
    assert "make reproduce" in CI, "reproduce job must run make reproduce"
    # The regenerated data must be re-validated by the full suite afterwards
    # (this is what stops the report drifting from what the code produces).
    tail = CI.split("make reproduce", 1)[1]
    assert "pytest -q" in tail, "reproduce job must re-run pytest after regenerating"
    # Clean must precede reproduce -- otherwise it is not from scratch.
    assert CI.index("make clean") < CI.index("make reproduce")


def test_report_documents_make_reproduce():
    text = (ROOT / "report" / "EMPIRICAL_STUDY.md").read_text(encoding="utf-8")
    assert "make reproduce" in text, "report section 7 must document `make reproduce`"
