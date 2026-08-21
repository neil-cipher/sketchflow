"""CIC-IDS-2017 loader — real intrusion-detection flows for SketchFlow.

Step 16 of plan.json — maps the CIC-IDS-2017 ML-format CSV into stream
keys that the SketchFlow engine can ingest.

The CIC-IDS-2017 MachineLearningCSV format (CICFlowMeter export) has 79
numeric flow features + a Label column, but **no raw IP addresses or
protocol field**.  Destination Port is the only network-header column.
This loader builds stream keys from Destination Port, which answers the
natural network-monitoring question: "which destination ports see the
most traffic?"

Usage::

    from sketchflow.cicids import load_cicids, load_cicids_flows

    # Simple: yields port-based stream keys for the engine
    for key in load_cicids("data/cicids_sample.csv"):
        engine.add(key)

    # Rich: yields dicts with port, label, duration for analysis
    for flow in load_cicids_flows("data/cicids_sample.csv"):
        engine.add(flow["key"])

Reference: Sharafaldin, Lashkari & Ghorbani, "Toward Generating a New
Intrusion Detection Dataset and Intrusion Detection Using Machine
Learning", ICISSP 2018.  Dataset from Canadian Institute for
Cybersecurity (UNB).
"""

from __future__ import annotations

import csv
import os
from typing import Iterator

__all__ = [
    "load_cicids",
    "load_cicids_flows",
    "CICIDS_COLUMNS",
    "DEFAULT_SAMPLE_PATH",
]

# Relative to repo root
DEFAULT_SAMPLE_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "cicids_sample.csv"
)

# The columns we care about (names after strip(); the CSV has leading spaces)
COL_DST_PORT = "Destination Port"
COL_LABEL = "Label"
COL_FLOW_DURATION = "Flow Duration"
COL_TOTAL_FWD_PKTS = "Total Fwd Packets"
COL_TOTAL_BWD_PKTS = "Total Backward Packets"

# Columns exported by the loader for inspection
CICIDS_COLUMNS = (COL_DST_PORT, COL_LABEL, COL_FLOW_DURATION,
                  COL_TOTAL_FWD_PKTS, COL_TOTAL_BWD_PKTS)


def _open_csv(path: str) -> tuple[csv.reader, list[str]]:
    """Open the CSV and return (reader, cleaned_header)."""
    fh = open(path, newline="", encoding="utf-8-sig")
    reader = csv.reader(fh)
    raw_header = next(reader)
    header = [col.strip() for col in raw_header]
    return reader, header


def _col_index(header: list[str], name: str) -> int:
    """Find column index by stripped name; raise ValueError if missing."""
    try:
        return header.index(name)
    except ValueError:
        raise ValueError(
            f"Column {name!r} not found in CSV header. "
            f"Available: {header[:10]}..."
        )


def load_cicids(path: str | None = None) -> Iterator[str]:
    """Yield stream keys from the CIC-IDS-2017 sample CSV.

    Each key is ``"port:<N>"`` where N is the Destination Port value.
    This is the only network-header column available in the ML-format CSV
    (no raw IPs or protocol field).

    Parameters
    ----------
    path : str or None
        Path to the CSV.  If None, uses the default sample at
        ``data/cicids_sample.csv`` relative to the repo root.

    Yields
    ------
    str
        Stream keys like ``"port:80"``, ``"port:443"``, ``"port:53"``.
    """
    if path is None:
        path = DEFAULT_SAMPLE_PATH
    reader, header = _open_csv(path)
    idx_port = _col_index(header, COL_DST_PORT)
    for row in reader:
        port = row[idx_port].strip()
        yield f"port:{port}"


def load_cicids_flows(path: str | None = None) -> Iterator[dict]:
    """Yield rich flow dicts from the CIC-IDS-2017 sample CSV.

    Each dict contains:

    - ``key``:  the stream key (``"port:<N>"``)
    - ``port``: raw destination port as int
    - ``label``: attack label string (e.g. ``"BENIGN"``,
      ``"Web Attack ... Brute Force"``)
    - ``duration``: flow duration in microseconds
    - ``fwd_pkts``: total forward packets
    - ``bwd_pkts``: total backward packets

    Parameters
    ----------
    path : str or None
        Path to the CSV.  If None, uses the default sample.

    Yields
    ------
    dict
        Flow record with key, port, label, duration, packet counts.
    """
    if path is None:
        path = DEFAULT_SAMPLE_PATH
    reader, header = _open_csv(path)
    idx_port = _col_index(header, COL_DST_PORT)
    idx_label = _col_index(header, COL_LABEL)
    idx_dur = _col_index(header, COL_FLOW_DURATION)
    idx_fwd = _col_index(header, COL_TOTAL_FWD_PKTS)
    idx_bwd = _col_index(header, COL_TOTAL_BWD_PKTS)

    for row in reader:
        port_str = row[idx_port].strip()
        yield {
            "key": f"port:{port_str}",
            "port": int(port_str),
            "label": row[idx_label].strip(),
            "duration": int(row[idx_dur].strip()),
            "fwd_pkts": int(row[idx_fwd].strip()),
            "bwd_pkts": int(row[idx_bwd].strip()),
        }
