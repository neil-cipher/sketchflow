"""Step 26 — static, self-contained coverage badge generator.

Why this module exists
----------------------
A coverage badge normally points at a third-party service (Codecov,
Coveralls) that needs an upload token. This project ships **no secrets**
and must stay verifiable from the repo alone, so the badge is generated
locally as a plain committed SVG instead.

What it does
------------
``make coverage`` runs the suite under ``coverage``, writes
``report/coverage.json`` (transient, git-ignored), then invokes this
module. It reads the measured total line-coverage percent and writes two
*committed* artifacts that must always agree (a test enforces it):

* ``report/coverage.svg``           — a shields-style flat badge.
* ``report/coverage_summary.json``  — the tiny data file behind the
  badge: the measured percent, the CI-enforced floor, and the Python
  version it was measured on.

The floor is read from ``.coveragerc`` (``[report] fail_under``) — the
single source of truth, the same number CI enforces with
``coverage report --fail-under``. Coverage is environment-dependent
(CPython version changes which lines exist, exactly like the memory
columns noted in step 24), so the honest, drift-proof claim is an
inequality: the badge shows a real measured snapshot, and CI proves the
live number never drops below the floor.

Run standalone:
    PYTHONPATH=src python -m sketchflow.covbadge            # from coverage.json
    PYTHONPATH=src python -m sketchflow.covbadge --pct 93   # explicit percent
"""

from __future__ import annotations

import argparse
import configparser
import json
import os
import platform
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.abspath(os.path.join(_HERE, "..", ".."))
_REPORT = os.path.join(_REPO, "report")
_COVERAGERC = os.path.join(_REPO, ".coveragerc")

DEFAULT_FLOOR = 90


def read_floor(coveragerc: str = _COVERAGERC) -> int:
    """The CI-enforced coverage floor, read from ``.coveragerc``.

    ``[report] fail_under`` is the single source of truth for the floor;
    CI enforces the identical number with ``--fail-under``.
    """
    parser = configparser.ConfigParser()
    if parser.read(coveragerc) and parser.has_option("report", "fail_under"):
        return int(round(float(parser.get("report", "fail_under"))))
    return DEFAULT_FLOOR


def read_measured_percent(coverage_json: str | None = None) -> float:
    """Measured total line-coverage percent, from ``coverage json`` output."""
    path = coverage_json or os.path.join(_REPORT, "coverage.json")
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    return float(data["totals"]["percent_covered"])


def _badge_color(pct: int, floor: int) -> str:
    if pct >= max(floor, 90):
        return "#4c1"          # bright green
    if pct >= 75:
        return "#a3c51c"       # yellow-green
    if pct >= 60:
        return "#dfb317"       # yellow
    return "#e05d44"           # red


def render_svg(pct: int, floor: int) -> str:
    """A minimal, dependency-free flat coverage badge (shields.io style)."""
    label = "coverage"
    message = f"{pct}%"
    # crude but stable text metrics (avg ~6.5px/char at font-size 11)
    label_w = 6 * len(label) + 10
    msg_w = 7 * len(message) + 10
    total_w = label_w + msg_w
    color = _badge_color(pct, floor)
    label_x = label_w * 10 // 2
    msg_x = (label_w * 10) + (msg_w * 10 // 2)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'width="{total_w}" height="20" role="img" '
        f'aria-label="{label}: {message}">'
        f'<title>{label}: {message}</title>'
        f'<linearGradient id="s" x2="0" y2="100%">'
        f'<stop offset="0" stop-color="#bbb" stop-opacity=".1"/>'
        f'<stop offset="1" stop-opacity=".1"/></linearGradient>'
        f'<clipPath id="r"><rect width="{total_w}" height="20" rx="3" fill="#fff"/></clipPath>'
        f'<g clip-path="url(#r)">'
        f'<rect width="{label_w}" height="20" fill="#555"/>'
        f'<rect x="{label_w}" width="{msg_w}" height="20" fill="{color}"/>'
        f'<rect width="{total_w}" height="20" fill="url(#s)"/></g>'
        f'<g fill="#fff" text-anchor="middle" '
        f'font-family="Verdana,Geneva,DejaVu Sans,sans-serif" '
        f'font-size="110" text-rendering="geometricPrecision">'
        f'<text aria-hidden="true" x="{label_x}" y="150" fill="#010101" '
        f'fill-opacity=".3" transform="scale(.1)" textLength="{(label_w - 10) * 10}">{label}</text>'
        f'<text x="{label_x}" y="140" transform="scale(.1)" '
        f'textLength="{(label_w - 10) * 10}">{label}</text>'
        f'<text aria-hidden="true" x="{msg_x}" y="150" fill="#010101" '
        f'fill-opacity=".3" transform="scale(.1)" textLength="{(msg_w - 10) * 10}">{message}</text>'
        f'<text x="{msg_x}" y="140" transform="scale(.1)" '
        f'textLength="{(msg_w - 10) * 10}">{message}</text>'
        f'</g></svg>\n'
    )


def write_badge(pct: int, floor: int | None = None) -> tuple[str, str]:
    """Write ``report/coverage.svg`` and ``report/coverage_summary.json``.

    Both are committed and MUST agree (tests/test_step26_ship.py enforces
    that the badge percent equals the summary percent and is >= floor).
    Returns the two paths written.
    """
    if floor is None:
        floor = read_floor()
    os.makedirs(_REPORT, exist_ok=True)

    svg_path = os.path.join(_REPORT, "coverage.svg")
    with open(svg_path, "w", encoding="utf-8") as fh:
        fh.write(render_svg(pct, floor))

    summary_path = os.path.join(_REPORT, "coverage_summary.json")
    summary = {
        "line_coverage_percent": pct,
        "floor": floor,
        "measured_python": platform.python_version(),
        "tool": "coverage.py",
        "note": (
            "Static, secret-free badge. Coverage is CPython-version "
            "dependent; this is a measured snapshot. CI enforces the "
            "floor with `coverage report --fail-under` on every push, so "
            "the live number never drops below `floor`."
        ),
    }
    with open(summary_path, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2)
        fh.write("\n")
    return svg_path, summary_path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Generate the coverage badge.")
    ap.add_argument(
        "--pct",
        type=float,
        default=None,
        help="Explicit coverage percent; if omitted, read report/coverage.json.",
    )
    ap.add_argument(
        "--coverage-json",
        default=None,
        help="Path to a coverage json report (default report/coverage.json).",
    )
    args = ap.parse_args(argv)

    if args.pct is not None:
        pct_raw = args.pct
    else:
        pct_raw = read_measured_percent(args.coverage_json)
    pct = int(round(pct_raw))

    floor = read_floor()
    svg_path, summary_path = write_badge(pct, floor)
    print(f"coverage badge: {pct}% (floor {floor}%) -> {svg_path}")
    print(f"coverage summary            -> {summary_path}")
    if pct < floor:
        print(
            f"WARNING: measured {pct}% is below the enforced floor {floor}%",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
