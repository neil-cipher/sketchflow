# SketchFlow — Empirical Study, v1

**A Count-Min Sketch I tried to break.** This report writes up the full empirical study: method, accuracy-vs-memory curves, two adversarial campaigns (a white-box collision attack and a realistic volumetric attack on real backbone traffic), and the honest limits of what was measured.

This is an **empirical study and reproducibility report, not a whitepaper**. It claims **no algorithmic novelty** — every structure here is 20+ years public domain [CM05, EV02, MAE05, B70] — and no patent angle exists or is claimed. The contribution is an honest, reproducible measurement of the textbook ε/δ guarantee under stress, including two conditions under which a deployed sketch's promise fails in practice while the theorem itself survives.

Every figure and table below is regenerated from committed code with pinned seeds; the exact one-line command is given next to each artifact. All 220 tests gate these results in CI.

---

## 1. Method

### 1.1 Structures under test (all from scratch, `src/sketchflow/`)

| Structure | File | Primary source |
|---|---|---|
| Count-Min Sketch (CMS): depth×width counters, min-query, inner product | `cms.py` | [CM05] |
| Conservative-update CMS (CU): bump only cells at the current minimum | `cu_cms.py` | [EV02] §4.2 |
| Space-Saving top-k: k monitored counters, min-eviction, heap+index | `space_saving.py` | [MAE05] |
| Bloom filter (warm-up only, not a headline) | `bloom.py` | [B70] |
| Tabulation hash family, chi²-uniformity and independence gated | `hashing.py` | [Z70, PT12] |
| Exact dict baseline (ground truth for every error number) | `baseline.py` | — |

ε/δ sizing follows the standard `width = ⌈e/ε⌉`, `depth = ⌈ln(1/δ)⌉` [CM05], implemented in `cms.py::size_cms` and tested in `tests/test_step6_cms_query_sizing.py`.

### 1.2 Workloads

- **Synthetic:** seeded Zipfian streams (`streams.py`), α=1.2 default, ground truth from the exact baseline. Zero downloads, fully reproducible.
- **Real trace 1 — MAWI** backbone pcap (WIDE samplepoint-B, 2006-01-05, trans-Pacific link) [MAWI]: 10,000 packets → 9,738 IP packets → 4,319 distinct 5-tuple flow keys via `mawi.py` (dpkt). `data/mawi_sample.pcap`, SHA-256 committed in `.project-meta/`.
- **Real trace 2 — CIC-IDS-2017** intrusion-detection flows [CIC17]: 10,180-row stratified sample (8,000 benign + 2,180 attack flows), destination-port keys via `cicids.py`. `data/cicids_sample.csv`, SHA-256 committed.
- **Adversarial:** two threat models, §3 and §4.

### 1.3 Measurement

- **Error:** per-key absolute/relative overestimation vs the exact baseline (`bench.py`). CMS never undercounts — a tested invariant, not an assumption (`tests/test_step5_cms_skeleton.py`).
- **Guarantee meter** (`guarantee_meter.py`): flags any key whose estimate exceeds `true + ε·N`; reports the empirical violation rate to compare directly against the promised δ.
- **Memory:** honest `sys.getsizeof`-recursive bytes (`cms.py::bytes_used`), compared against the Python dict baseline — Python object overhead included on both sides.

---

## 2. Result: accuracy vs memory (benign)

**Artifact:** `report/sweep.csv` (32 rows) and `report/accuracy_vs_memory.png` — regenerate with `PYTHONPATH=src python -m sketchflow.plot`.

ε swept over two orders of magnitude (0.1 → 0.0005), 4 variants (CMS, CU-CMS, Engine, Engine-CU), 50k-event Zipfian stream, seed 42:

- Error decays roughly linearly on log-log axes as ε shrinks, matching the O(ε·N) bound's shape [CM05].
- **Conservative update roughly halves mean error at every memory point** (e.g. ε=0.1: 581.1 → 331.4; ε=0.001: 0.230 → 0.055) — consistent with [EV02] and the modern CU-analysis line of work cited in the README, which we reproduce but do not extend.
- **Honest memory finding:** at ε=0.001 the sketch (473 KB) already exceeds the exact dict baseline (memory ratio 1.12), and at ε=0.0005 it is 2.2× the baseline. In pure Python, sub-linear memory is only real at moderate ε; per-counter object overhead eats the asymptotic win at tight ε. A C array implementation would move this crossover, but we report what we measured.

## 3. Result: benign streams keep the δ promise

**Code:** `guarantee_meter.py::benign_violation_study`; gated in `tests/test_step20_guarantee_meter.py`.

At ε=0.01, δ=0.05, across **300 independent hash seeds** on a 10k Zipfian stream, every one of the top-10 heavy-hitter keys measured a **0.0 empirical violation rate** — comfortably inside the δ=0.05 promise. This reproduces the textbook expectation [CM05] and calibrates the meter used in §4–5: the meter reads ~0 exactly where theory says it should.

## 4. Result: white-box collision attack (CU is not a defense)

**Threat model:** an attacker who knows the sketch's exact `(width, depth, seed)` — the hash-flooding model of [CW03] — brute-force searches for keys that share the same bucket in **every** row (`adversary.py::find_colliding_group`).

**Artifact:** `report/adversarial.csv` (40 rows, 10 seeds) — regenerate with `PYTHONPATH=src python -m sketchflow.adversarial_study`.

On a deliberately small demo sketch (width 16, depth 3, ε=0.02; the attack search is tractable only there — see §6):

| Variant | Stream | Violation rate | Mean error |
|---|---|---|---|
| CMS | adversarial | **1.000** | 82.0 |
| CU-CMS | adversarial | **1.000** | 80.0 |
| CMS | size-matched control | 0.464 | 11.0 |
| CU-CMS | size-matched control | 0.000 | 2.0 |

**Finding:** conservative update **does not survive** the attack. Full-row collision groups make every group member share the same cell in every row, so CU's "trust the cleanest row" trick has no cleaner row left — it degenerates into plain CMS (mean error 80.0 vs 82.0, no rescue), while keeping its usual benign-stream edge (0.000 vs 0.464 violation on the control). Robustness against a known-seed attacker must come from **sizing plus a secret, re-randomizable seed**, not from CU. The flip-side check in `adversary.py` confirms the same search fails within 5,000 candidate trials against a production-sized sketch (`size_cms(0.01, 0.05)` → width 272).

## 5. Result: volumetric attack on real traffic (which promise breaks)

**Threat model:** weaker and more realistic — the attacker knows nothing about the sketch and only **amplifies flows that are already heavy** (the volumetric DDoS pattern), on the two real traces. `real_adversary.py` sweeps amplification factor {1, 2, 5, 10, 20, 50} × provisioning {well-sized ε=0.01 (w=272), under-provisioned ε=0.1 (w=28)}.

**Artifact:** `report/real_adversarial.csv` (24 rows) and `report/real_adversarial.png` — regenerate with `PYTHONPATH=src python -m sketchflow.real_plot`.

Two distinct promises are measured per row: the **theorem bound** ε·N (N = live stream length, self-scaling) and the **operator's provisioned promise** ε·N₀ (N₀ = the baseline length the sketch was sized for, fixed at deployment).

- **A well-sized sketch is essentially immune** to ×50 amplification on real traffic: MAWI mean error 22.2 → 23.0; CIC-IDS flat at 3.34 (the amplified top ports occupy uncontested buckets); provisioned violation ≈ 0.
- **Under-provisioning breaks the operator's fixed promise:** at ×50, 3.4% of MAWI flows and 2.4% of CIC-IDS flows violate ε·N₀, with mean error climbing to 401.6 (MAWI) and 163.1 (CIC-IDS).
- **The self-scaling textbook bound holds everywhere** (max theorem violation rate 0.0009 across all 24 cells): ε·N loosens exactly as fast as N grows, so volume alone cannot break the theorem [CM05]. Proven per-row invariant: `violation_rate_theorem ≤ violation_rate_provisioned`, since N ≥ N₀.

**Finding:** "the attacker broke the sketch" is the wrong summary. The attack breaks the **operator's one-time sizing decision**, never the theorem. Practical defense is provisioning for peak (or re-sizing under load) — not conservative update (§4) and not the bound itself.

## 6. Honest limits

- **The §4 attack runs on a toy sketch.** Full-row collision search is exponential-ish in depth×width; we show it fails against a production-sized sketch within our search budget, but a stronger attacker (more compute, cleverer search, e.g. multicollision techniques) is not ruled out — [CW03]-style attacks have historically improved.
- **Pure-Python memory numbers.** The §2 memory crossover (sketch > dict at tight ε) is a fact about CPython object overhead, not about the algorithm; C implementations would differ. We report measured bytes, both sides Python.
- **Small real-trace samples.** 10k packets (MAWI) and 10,180 flows (CIC-IDS) are samples chosen for repo-committable reproducibility, not full-day traces; heavy-hitter structure at full scale may differ. Both files carry committed SHA-256 hashes.
- **MAWI trace is from 2006** (chosen: stable no-login archive URL); traffic mix is dated, though the sketch-vs-volume question is structural rather than era-specific.
- **One α, mostly one stream length** for the benign curves (α=1.2, 50k); the sweep varies ε/memory, not workload shape.
- **δ-side coverage:** the benign study measures top-10 heavy-hitter keys across 300 seeds; tail-key violation behavior is exercised by the meter's full-key mode but not swept as exhaustively.
- **No claim extends the CU-CMS literature** (INRIA; IEEE 2022; arXiv:2405.12034; SIGMETRICS 2025 — see README). We reproduce known behavior and add stress measurements.

## 7. Reproducing everything

```
git clone https://github.com/neil-cipher/sketchflow && cd sketchflow
pip install pytest matplotlib dpkt
PYTHONPATH=src python -m pytest -q            # 220 tests
PYTHONPATH=src python -m sketchflow.bench     # report/results.csv
PYTHONPATH=src python -m sketchflow.plot      # report/sweep.csv + accuracy_vs_memory.png
PYTHONPATH=src python -m sketchflow.adversarial_study   # report/adversarial.csv
PYTHONPATH=src python -m sketchflow.real_plot           # report/real_adversarial.csv + .png
```

All randomness is seeded; the CSVs committed in `report/` are byte-reproducible from the commands above.

## References

- **[CM05]** G. Cormode, S. Muthukrishnan. *An improved data stream summary: the count-min sketch and its applications.* J. Algorithms 55(1), 2005.
- **[EV02]** C. Estan, G. Varghese. *New directions in traffic measurement and accounting.* ACM SIGCOMM 2002, §4.2 (conservative update).
- **[MAE05]** A. Metwally, D. Agrawal, A. El Abbadi. *Efficient computation of frequent and top-k elements in data streams.* ICDT 2005 (Space-Saving).
- **[B70]** B. H. Bloom. *Space/time trade-offs in hash coding with allowable errors.* CACM 13(7), 1970.
- **[CW03]** S. A. Crosby, D. S. Wallach. *Denial of service via algorithmic complexity attacks.* USENIX Security 2003.
- **[Z70]** A. L. Zobrist. *A new hashing method with application for game playing.* Univ. of Wisconsin TR 88, 1970 (tabulation hashing).
- **[PT12]** M. Pătraşcu, M. Thorup. *The power of simple tabulation hashing.* J. ACM 59(3), 2012.
- **[MAWI]** WIDE Project MAWI Working Group traffic archive, samplepoint-B, 2006-01-05. mawi.wide.ad.jp.
- **[CIC17]** I. Sharafaldin, A. H. Lashkari, A. A. Ghorbani. *Toward generating a new intrusion detection dataset and intrusion traffic characterization.* ICISSP 2018 (CIC-IDS-2017).
