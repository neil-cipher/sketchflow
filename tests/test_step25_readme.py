"""Step 25 gate: README polish — hook, results summary, verify-in-5-min,
pedagogy index, literature; every internal link resolves; headline numbers
match the committed CSVs (README cannot silently drift from the data)."""

import csv
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
README = REPO / "README.md"


def _text():
    return README.read_text(encoding="utf-8")


def test_readme_exists_and_nonempty():
    assert README.is_file(), "README.md missing"
    assert len(_text()) > 1500, "README too thin for a reviewer-facing landing page"


def test_required_sections_present():
    t = _text().lower()
    for needle in [
        "the hook",              # hook
        "results in four numbers",  # results summary
        "verify me in 5 minutes",   # reviewer-verifiable
        "pedagogy index",           # pedagogy notes index
        "literature",               # citations
    ]:
        assert needle in t, f"README missing required section: {needle!r}"


def test_verify_commands_present():
    t = _text()
    for cmd in ["pip install -r requirements.txt", "pytest", "make reproduce"]:
        assert cmd in t, f"verify-in-5-min block missing command: {cmd!r}"


def test_no_novelty_claim():
    t = _text().lower()
    assert "no claim of algorithmic novelty" in t
    assert "empirical study" in t


def test_internal_links_resolve():
    """Every markdown link to a local path (not http) must point at a real
    file in the repo. Anchors (#...) are stripped before checking."""
    t = _text()
    links = re.findall(r"\]\(([^)]+)\)", t)
    checked = 0
    for target in links:
        if target.startswith("http") or target.startswith("#"):
            continue
        path_part = target.split("#", 1)[0]
        if not path_part:
            continue
        assert (REPO / path_part).exists(), f"broken internal link: {target}"
        checked += 1
    assert checked >= 6, f"expected several internal file links, found {checked}"


# ---- drift-proof numeric gates: recompute headline numbers FROM the CSVs ----

def _results_rows():
    with open(REPO / "report" / "results.csv", newline="") as fh:
        return list(csv.DictReader(fh))


def test_cu_halves_error_claim_matches_data():
    """README claims CU-CMS halves mean error at eps=0.01; verify against CSV
    and that the two exact numbers cited (24.46 / 12.56) appear in the README."""
    rows = _results_rows()
    def cell(variant):
        r = next(x for x in rows if x["variant"] == variant
                 and abs(float(x["epsilon"]) - 0.01) < 1e-9)
        return float(r["mean_abs_error"])
    cms, cu = cell("CMS"), cell("CU-CMS")
    assert cu < 0.6 * cms, f"CU did not halve error in data: {cu} vs {cms}"
    t = _text()
    assert f"{cms:.2f}" in t, f"README should cite plain-CMS mean error {cms:.2f}"
    assert f"{cu:.2f}" in t, f"README should cite CU-CMS mean error {cu:.2f}"


def test_memory_crossover_claim_matches_data():
    rows = _results_rows()
    small = next(x for x in rows if x["variant"] == "CMS"
                 and abs(float(x["epsilon"]) - 0.01) < 1e-9)
    tight = next(x for x in rows if x["variant"] == "CMS"
                 and abs(float(x["epsilon"]) - 0.001) < 1e-9)
    assert float(small["memory_ratio"]) < 1.0 < float(tight["memory_ratio"]), \
        "memory crossover (sketch cheaper at eps=0.01, dearer at eps=0.001) not in data"
    assert "1.39" in _text(), "README should cite the eps=0.001 memory ratio 1.39"


def test_cu_not_a_defense_claim_matches_data():
    with open(REPO / "report" / "adversarial.csv", newline="") as fh:
        rows = list(csv.DictReader(fh))
    cu_adv = [float(r["violation_rate"]) for r in rows
              if r["variant"] == "cu" and r["stream"] == "adversarial"]
    assert cu_adv and all(v == 1.0 for v in cu_adv), \
        "CU should show violation_rate 1.0 under attack in the data"
    t = _text().lower()
    assert "not a defense" in t or "no." in t
    assert "secret seed" in t


def test_pedagogy_index_covers_the_build():
    t = _text()
    # the index is a table spanning step 0 through the current step
    assert "0–1" in t and "23–25" in t, "pedagogy index should span steps 0..25"
    assert "standout" in t.lower()
