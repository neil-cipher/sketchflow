# SketchFlow — FROZEN SPEC (read-only for every daily run)
**Frozen:** 27-Jul-2026 · **Owner:** Suds · **Builder-of-record:** Ishan Neil Bhargav · **GitHub:** `neil-cipher` · **Repo:** `neil-cipher/sketchflow`
**Semester context:** VIT Sem-1, only CS course = BCSE101E Python. Engine stays GENTLE until after CAT-1 (09-Aug-2026), then ramps.
**This file is immutable.** A daily run may advance the step pointer or raise a blocker. It may NOT redefine the project, re-order the plan, or invent steps (Rule 1). Scope drift = P0 bug.

---

## One-line identity
**A Count-Min Sketch you can *break*** — a from-scratch sublinear stream-counting engine whose headline is not "I implemented the structure" but "I built an adversarial workload that stresses the ε/δ error guarantee and measured exactly where the textbook bound holds and where it fails, on real backbone-network traffic."

## Standout hook (the line a reviewer stops scrolling for)
> "A Count-Min Sketch I tried to break — an adversarial stream generator that stresses the error bound, benchmarked on real backbone traffic (MAWI), showing where the textbook ε/δ guarantee holds and where it doesn't."

## Why this, and the honesty guardrails (skeptic-audited 27-Jul)
- **ONE hero structure, not a zoo.** Spine = **Count-Min Sketch (CMS)** + its **conservative-update (CU-CMS)** variant. Companion = **Space-Saving** for top-k heavy hitters. A **Bloom filter** appears only as an early Sem-1-friendly warm-up (a "have I seen this flow?" gate), NOT as a headline. **HyperLogLog is explicitly OUT of the core** — demoted to an optional post-core stretch (step 27+), clearly labelled, because its bias-correction math is not honestly buildable-from-scratch six weeks into Python. Implementing four textbook structures is breadth theater and is saturated on student GitHubs — deliberately avoided.
- **The contribution is empirical, not theoretical.** CU-CMS analysis is an active academic subfield (INRIA; IEEE 2022; arXiv 2405.12034 2024; ACM SIGMETRICS 2025). Ishan does NOT claim to advance it. He *cites* it in the README to show literature awareness, and contributes an **honest reproducibility + adversarial-stress study**: rebuild the known ε-vs-memory curves, then push past them with a workload that intentionally attacks the guarantee.
- **Deliverable is an "empirical study / reproducibility + stress report," NOT a "whitepaper."** Under-claiming beats over-claiming on a public recruiter-facing repo. **Patent: NO** (algorithms are 20+ years public domain — and the README says so).
- **~28 substantive steps, not 64.** Daily micro-commit farming reads as manufactured; each committed step must add real, tested capability.
- **Datasets de-risked.** Phase 1 uses a **synthetic Zipfian stream generator** (10-line, ground-truth-checkable, zero downloads, no admin/root). Real data added only after the core is green: **CIC-IDS-2017** via the zero-gatekeeping **Kaggle mirror** (pre-extracted CSV flow features) and **MAWI** daily pcaps (mawi.wide.ad.jp, no login). Raw self-capture (scapy/root) is OPTIONAL and never on the critical path (it triggers an admin/Npcap human-in-loop wall).

## What "done / standout" means for THIS project (the bar it must clear — Rule 10)
A FAANG/Marquee reviewer AND an MS admissions committee can BOTH independently verify, from the repo alone:
1. CMS, CU-CMS, and Space-Saving are implemented correctly from scratch (tests prove estimate ≥ true count; error within ε·N w.h.p.).
2. There is a reproducible benchmark harness (exact dict/set baseline vs sketch) producing accuracy-vs-memory curves.
3. There is an **adversarial stream generator** and a written finding on where the ε/δ bound is tight vs loose — a result not merely re-plotted from the papers.
4. It runs on at least one real backbone-traffic source, not only synthetic data.
5. Every non-trivial factual claim in README/report carries a primary-source citation.
This clears a HIGHER CS-core bar than the IITK cyber packet (applied-security tooling) by adding algorithmic rigor, error-bound reasoning, and reproducible benchmarking — provided the one-structure-deep version is kept. The network-traffic framing is the deliberate bridge from his packet/cyber past.

## Core components (frozen scope — nothing outside this list)
1. `hashing.py` — a small family of independent hash functions (tabulation / multiply-shift), tested for the pairwise-independence the CMS bound assumes.
2. `bloom.py` — Bloom filter (bit array + k hashes) — warm-up only.
3. `count_min.py` — Count-Min Sketch: 2D counter array, k rows, min-estimate query, ε/δ ↔ (width, depth) sizing, point-query + inner-product.
4. `cu_count_min.py` — conservative-update variant (increment only the minimum cells).
5. `space_saving.py` — Space-Saving top-k (bounded min-heap + hash index; monitored-counter eviction).
6. `baseline.py` — exact `dict`/`set` ground-truth counter for correctness + memory comparison.
7. `streams.py` — stream sources: synthetic Zipfian generator (seeded, ground-truth), then real-trace loaders (CIC-IDS CSV, MAWI pcap → 5-tuple flow keys).
8. `adversary.py` — the standout: generators that deliberately stress CMS (collision-maximising heavy-hitter placement, low-δ regimes) and measure guarantee violation rate.
9. `bench.py` + `report/` — reproducible harness → CSV + plots + the written empirical/stress report (Markdown).

## Non-goals (explicitly excluded, to prevent scope drift)
- No web UI / dashboard / API server. No real-time packet sniffer as a headline (optional side-quest only).
- No HyperLogLog in core. No fourth/fifth structure. No "whitepaper" / patent framing. No ML/anomaly-detection classifier.
- No claim of algorithmic novelty in CU-CMS.

## Pedagogy contract (Rule 10)
Every step ships a 4-line layman note: what was built / why it matters / the CS concept it drills / what's next. Teaching Ishan to run the next project himself is as mandatory as the code. Notes land in `.project-meta/decisions.log` and in the page's per-step strip.

## Alternatives considered and rejected at selection (audit trail)
- **Aho-Corasick multi-pattern IDS matcher** — strongest runner-up; tighter continuation of his security thread. Kept as the intended **Sem-2 sequel**, not Sem-1 hero (narrower benchmark story for a first flagship).
- **LSM-tree / B-tree + WAL mini-KV store** — rarer on student GitHubs, great "systems" signal, but durability + rebalancing is heavier than the CMS core for a Sem-1 fresher.
- **Patricia/LC-trie IP router** — good packet-interest fit; thinner benchmarking narrative.
- **All-four probabilistic-DS zoo (original pitch)** — REJECTED: saturated, reads as four tutorials, no reviewer hook.
