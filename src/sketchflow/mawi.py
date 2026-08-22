"""MAWI pcap loader — real backbone traffic for SketchFlow.

Step 18 of plan.json — parses the MAWI Working Group pcap sample into
5-tuple flow keys that the SketchFlow engine can ingest.

The pcap was captured at WIDE Project samplepoint-B (trans-Pacific link,
Jan 2006).  IPs are scrambled by tcpdpriv (privacy), snaplen=96 bytes.
Linktype=1 (Ethernet).

Usage::

    from sketchflow.mawi import load_mawi, load_mawi_packets

    # Simple: yields 5-tuple flow keys for the engine
    for key in load_mawi("data/mawi_sample.pcap"):
        engine.add(key)

    # Rich: yields dicts with IPs, ports, protocol, timestamp
    for pkt in load_mawi_packets("data/mawi_sample.pcap"):
        engine.add(pkt["key"])

Reference: MAWI Working Group Traffic Archive, WIDE Project.
http://mawi.wide.ad.jp/mawi/
"""

from __future__ import annotations

import os
import socket
from typing import Iterator

import dpkt

__all__ = [
    "load_mawi",
    "load_mawi_packets",
    "DEFAULT_PCAP_PATH",
]

# Relative to repo root
DEFAULT_PCAP_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "mawi_sample.pcap"
)

# Protocol number → short name (for readable keys)
_PROTO_NAMES = {
    1: "ICMP",
    6: "TCP",
    17: "UDP",
    47: "GRE",
    50: "ESP",
    58: "ICMPv6",
}


def _proto_label(num: int) -> str:
    """Human-readable protocol label."""
    return _PROTO_NAMES.get(num, f"proto{num}")


def _make_key(src_ip: str, dst_ip: str,
              sport: int, dport: int, proto: str) -> str:
    """Build a canonical 5-tuple flow key string.

    Format: ``"src_ip:sport->dst_ip:dport/PROTO"``
    For non-port protocols (ICMP etc.): ``"src_ip->dst_ip/PROTO"``
    """
    if sport == 0 and dport == 0:
        return f"{src_ip}->{dst_ip}/{proto}"
    return f"{src_ip}:{sport}->{dst_ip}:{dport}/{proto}"


def load_mawi(path: str | None = None) -> Iterator[str]:
    """Yield 5-tuple flow keys from the MAWI pcap sample.

    Each key encodes (src_ip, src_port, dst_ip, dst_port, protocol).
    TCP and UDP packets get full 5-tuple keys; ICMP and other protocols
    get IP-pair keys with protocol label (ports = 0).

    Non-IP packets (ARP, etc.) are skipped.

    Parameters
    ----------
    path : str or None
        Path to the pcap.  If None, uses the default sample at
        ``data/mawi_sample.pcap`` relative to the repo root.

    Yields
    ------
    str
        Flow keys like ``"1.2.3.4:80->5.6.7.8:443/TCP"`` or
        ``"1.2.3.4->5.6.7.8/ICMP"``.
    """
    if path is None:
        path = DEFAULT_PCAP_PATH

    with open(path, "rb") as f:
        pcap = dpkt.pcap.Reader(f)
        for _ts, buf in pcap:
            try:
                eth = dpkt.ethernet.Ethernet(buf)
            except (dpkt.UnpackError, dpkt.NeedData):
                continue

            if not isinstance(eth.data, dpkt.ip.IP):
                continue  # skip ARP, IPv6, etc.

            ip = eth.data
            src_ip = socket.inet_ntoa(ip.src)
            dst_ip = socket.inet_ntoa(ip.dst)
            proto_num = ip.p
            proto_label = _proto_label(proto_num)

            # Try to extract ports from transport layer
            if isinstance(ip.data, (dpkt.tcp.TCP, dpkt.udp.UDP)):
                sport = ip.data.sport
                dport = ip.data.dport
            elif proto_num in (6, 17):
                # Truncated TCP/UDP — dpkt couldn't parse transport header
                # but IP header says it's TCP/UDP.  Ports unknown.
                sport, dport = 0, 0
            else:
                sport, dport = 0, 0

            yield _make_key(src_ip, dst_ip, sport, dport, proto_label)


def load_mawi_packets(path: str | None = None) -> Iterator[dict]:
    """Yield rich packet dicts from the MAWI pcap sample.

    Each dict contains:

    - ``key``:       the 5-tuple flow key string
    - ``src_ip``:    source IP (scrambled)
    - ``dst_ip``:    destination IP (scrambled)
    - ``src_port``:  source port (0 for non-port protocols)
    - ``dst_port``:  destination port (0 for non-port protocols)
    - ``proto``:     protocol label (``"TCP"``, ``"UDP"``, ``"ICMP"``, …)
    - ``proto_num``: raw IP protocol number
    - ``timestamp``: pcap timestamp (float, seconds since epoch)
    - ``length``:    captured packet length in bytes

    Parameters
    ----------
    path : str or None
        Path to the pcap.  If None, uses the default sample.

    Yields
    ------
    dict
        Packet record with key, IPs, ports, protocol, timestamp, length.
    """
    if path is None:
        path = DEFAULT_PCAP_PATH

    with open(path, "rb") as f:
        pcap = dpkt.pcap.Reader(f)
        for ts, buf in pcap:
            try:
                eth = dpkt.ethernet.Ethernet(buf)
            except (dpkt.UnpackError, dpkt.NeedData):
                continue

            if not isinstance(eth.data, dpkt.ip.IP):
                continue

            ip = eth.data
            src_ip = socket.inet_ntoa(ip.src)
            dst_ip = socket.inet_ntoa(ip.dst)
            proto_num = ip.p
            proto_label = _proto_label(proto_num)

            if isinstance(ip.data, (dpkt.tcp.TCP, dpkt.udp.UDP)):
                sport = ip.data.sport
                dport = ip.data.dport
            elif proto_num in (6, 17):
                sport, dport = 0, 0
            else:
                sport, dport = 0, 0

            key = _make_key(src_ip, dst_ip, sport, dport, proto_label)

            yield {
                "key": key,
                "src_ip": src_ip,
                "dst_ip": dst_ip,
                "src_port": sport,
                "dst_port": dport,
                "proto": proto_label,
                "proto_num": proto_num,
                "timestamp": ts,
                "length": len(buf),
            }
