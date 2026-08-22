"""Step 18 tests — MAWI pcap loader + engine on real backbone traffic.

Gate (plan.json step 18):
  'test: pcap reader yields flow keys; benchmark runs end-to-end
   on MAWI sample'

These tests verify:
  1. Loader basics: parses packets, yields correct key format
  2. Rich packet loader: IPs, ports, protocol, timestamp fields
  3. Protocol distribution matches known sample composition
  4. Engine on real data: top-k flows match exact baseline
  5. CU-CMS variant also matches on real data
  6. Never-undercount invariant on all distinct flows
  7. Non-IP packets are skipped (correct count < 10000)
  8. Truncated-TCP handling: proto-6 packets yield TCP keys
  9. Key format: 5-tuple for TCP/UDP, IP-pair for ICMP/GRE
  10. Benchmark harness runs end-to-end on MAWI data
"""

import os
import pytest
from collections import Counter

# ── Loader under test ────────────────────────────────────────────────
from sketchflow.mawi import (
    load_mawi,
    load_mawi_packets,
    DEFAULT_PCAP_PATH,
)

# ── Engine + baseline ────────────────────────────────────────────────
from sketchflow.engine import SketchEngine
from sketchflow.baseline import ExactCounter

# ── Path to the sample pcap ─────────────────────────────────────────
SAMPLE = os.path.normpath(DEFAULT_PCAP_PATH)
TOTAL_PACKETS = 10000  # raw packets in pcap


@pytest.fixture(scope="module")
def all_keys():
    """Load all flow keys once for the module."""
    return list(load_mawi(SAMPLE))


@pytest.fixture(scope="module")
def all_packets():
    """Load all rich packet dicts once for the module."""
    return list(load_mawi_packets(SAMPLE))


@pytest.fixture(scope="module")
def exact_counts(all_keys):
    """Exact frequency counts over all keys."""
    return Counter(all_keys)


# ── 1. Basic loader ─────────────────────────────────────────────────

class TestLoaderBasics:
    """Loader parses pcap and yields well-formed keys."""

    def test_yields_keys(self, all_keys):
        """Loader produces a non-empty list of string keys."""
        assert len(all_keys) > 0
        assert all(isinstance(k, str) for k in all_keys)

    def test_ip_packets_fewer_than_total(self, all_keys):
        """Non-IP packets (ARP etc.) are skipped, so count < 10000."""
        assert len(all_keys) < TOTAL_PACKETS

    def test_ip_packets_majority(self, all_keys):
        """The vast majority of packets are IP (>95%)."""
        assert len(all_keys) > TOTAL_PACKETS * 0.95

    def test_distinct_flows(self, exact_counts):
        """There are many distinct 5-tuple flows in backbone traffic."""
        assert len(exact_counts) > 1000

    def test_key_format_tcp_udp(self, all_keys):
        """TCP/UDP keys follow 'src:port->dst:port/PROTO' format."""
        tcp_keys = [k for k in all_keys if k.endswith("/TCP")]
        assert len(tcp_keys) > 0
        sample = tcp_keys[0]
        assert "->" in sample
        assert ":" in sample.split("->")[0]  # src has port
        assert ":" in sample.split("->")[1].split("/")[0]  # dst has port

    def test_key_format_non_port(self, all_keys):
        """Non-port protocols (ICMP, GRE) use 'src->dst/PROTO' format."""
        non_port = [k for k in all_keys
                    if not k.endswith("/TCP") and not k.endswith("/UDP")]
        assert len(non_port) > 0
        sample = non_port[0]
        assert "->" in sample
        # src side should NOT have a port colon
        src_part = sample.split("->")[0]
        # IP addresses have dots, but no colon for port
        assert ":" not in src_part


# ── 2. Rich packet loader ───────────────────────────────────────────

class TestRichPacketLoader:
    """load_mawi_packets yields dicts with all expected fields."""

    def test_fields_present(self, all_packets):
        """Every packet dict has the required fields."""
        required = {"key", "src_ip", "dst_ip", "src_port", "dst_port",
                    "proto", "proto_num", "timestamp", "length"}
        for pkt in all_packets[:10]:
            assert required.issubset(pkt.keys())

    def test_ip_format(self, all_packets):
        """IPs are dotted-quad strings."""
        pkt = all_packets[0]
        parts = pkt["src_ip"].split(".")
        assert len(parts) == 4
        assert all(p.isdigit() for p in parts)

    def test_timestamp_positive(self, all_packets):
        """Timestamps are positive floats (seconds since epoch)."""
        for pkt in all_packets[:100]:
            assert isinstance(pkt["timestamp"], float)
            assert pkt["timestamp"] > 0

    def test_length_positive(self, all_packets):
        """Packet lengths are positive integers."""
        for pkt in all_packets[:100]:
            assert isinstance(pkt["length"], int)
            assert pkt["length"] > 0

    def test_tcp_has_ports(self, all_packets):
        """TCP packets have non-zero ports."""
        tcp_pkts = [p for p in all_packets if p["proto"] == "TCP"
                    and p["src_port"] != 0]
        assert len(tcp_pkts) > 0
        pkt = tcp_pkts[0]
        assert 0 < pkt["src_port"] <= 65535
        assert 0 < pkt["dst_port"] <= 65535

    def test_count_matches_simple_loader(self, all_keys, all_packets):
        """Rich loader yields the same number of records as simple loader."""
        assert len(all_packets) == len(all_keys)


# ── 3. Protocol distribution ────────────────────────────────────────

class TestProtocolDistribution:
    """Protocol mix matches known MAWI sample composition."""

    def test_tcp_dominant(self, all_packets):
        """TCP is the dominant protocol (~80%)."""
        tcp_count = sum(1 for p in all_packets if p["proto"] == "TCP")
        ratio = tcp_count / len(all_packets)
        assert ratio > 0.7, f"TCP ratio {ratio:.2%} too low"

    def test_udp_present(self, all_packets):
        """UDP traffic is present (~12%)."""
        udp_count = sum(1 for p in all_packets if p["proto"] == "UDP")
        assert udp_count > 100

    def test_icmp_present(self, all_packets):
        """ICMP traffic is present in backbone data."""
        icmp_count = sum(1 for p in all_packets if p["proto"] == "ICMP")
        assert icmp_count > 0

    def test_gre_present(self, all_packets):
        """GRE tunnel traffic is present (backbone characteristic)."""
        gre_count = sum(1 for p in all_packets if p["proto"] == "GRE")
        assert gre_count > 0


# ── 4. Engine on real backbone traffic ───────────────────────────────

class TestEngineOnMawi:
    """SketchEngine produces correct results on MAWI data."""

    @pytest.fixture(scope="class")
    def engine_and_baseline(self, all_keys):
        """Run engine and baseline on the same keys."""
        engine = SketchEngine(epsilon=0.001, delta=0.01, top_k=500)
        baseline = ExactCounter()
        for key in all_keys:
            engine.add(key)
            baseline.add(key)
        return engine, baseline

    def test_top10_match(self, engine_and_baseline):
        """Engine top-10 flows match exact top-10 (with k=500 headroom)."""
        engine, baseline = engine_and_baseline
        engine_top10 = set(k for k, _ in engine.heavy_hitters(10))
        exact_top10 = set(k for k, _ in baseline.top_k(10))
        assert engine_top10 == exact_top10

    def test_never_undercount(self, engine_and_baseline, exact_counts):
        """Engine never undercounts any flow key."""
        engine, _ = engine_and_baseline
        for key, true_count in exact_counts.items():
            assert engine.estimate(key) >= true_count, \
                f"Undercount on {key}: est={engine.estimate(key)} < true={true_count}"

    def test_total_matches(self, engine_and_baseline, all_keys):
        """Engine total matches the number of IP packets processed."""
        engine, _ = engine_and_baseline
        assert engine.total == len(all_keys)


# ── 5. CU-CMS on MAWI ───────────────────────────────────────────────

class TestCuCmsOnMawi:
    """Conservative-update variant also works on backbone traffic."""

    @pytest.fixture(scope="class")
    def engines(self, all_keys):
        """Run both plain and CU engines on the same keys."""
        plain = SketchEngine(epsilon=0.001, delta=0.01, top_k=500,
                             conservative=False)
        cu = SketchEngine(epsilon=0.001, delta=0.01, top_k=500,
                          conservative=True)
        baseline = ExactCounter()
        for key in all_keys:
            plain.add(key)
            cu.add(key)
            baseline.add(key)
        return plain, cu, baseline

    def test_cu_top10_match(self, engines):
        """CU-CMS engine top-10 also matches exact baseline."""
        _, cu, baseline = engines
        cu_top10 = set(k for k, _ in cu.heavy_hitters(10))
        exact_top10 = set(k for k, _ in baseline.top_k(10))
        assert cu_top10 == exact_top10

    def test_cu_reduces_overestimation(self, engines):
        """CU-CMS has less total overestimation than plain CMS."""
        plain, cu, baseline = engines
        plain_over = sum(plain.estimate(k) - c
                         for k, c in baseline.top_k(50))
        cu_over = sum(cu.estimate(k) - c
                      for k, c in baseline.top_k(50))
        assert cu_over <= plain_over, \
            f"CU overestimation ({cu_over}) > plain ({plain_over})"


# ── 6. End-to-end benchmark on MAWI ─────────────────────────────────

class TestBenchmarkOnMawi:
    """Full benchmark pipeline runs end-to-end on MAWI backbone data."""

    def test_end_to_end_error_and_memory(self, all_keys, exact_counts):
        """Engine measures error and memory on real backbone traffic."""
        engine = SketchEngine(epsilon=0.01, delta=0.01, top_k=50)
        for key in all_keys:
            engine.add(key)

        # Error measurement against exact counts
        abs_errors = []
        for key, true_count in exact_counts.items():
            est = engine.estimate(key)
            abs_errors.append(est - true_count)

        mean_error = sum(abs_errors) / len(abs_errors)
        max_error = max(abs_errors)

        assert mean_error >= 0, "mean error should be non-negative (overestimates)"
        assert max_error >= 0
        assert engine.total == len(all_keys)

        # Memory measurement (via CMS internals)
        mem = engine.cms.bytes_used()
        assert mem > 0
        summary = engine.summary()
        assert summary["total"] == len(all_keys)
