# SketchFlow — a Count-Min Sketch you can *break*

A from-scratch, sublinear **stream-counting engine** for network traffic — built one honest step at a time.

> **The hook:** most "probabilistic data structure" repos implement Count-Min Sketch, Bloom, HyperLogLog and stop. SketchFlow does the opposite of breadth: it takes **one** structure — the Count-Min Sketch (and its conservative-update variant) — and **tries to break it.** An adversarial stream generator deliberately stresses the ε/δ error guarantee, and the engine measures **where the textbook bound holds and where it fails**, on real backbone-network traffic (MAWI, CIC-IDS-2017).

This is an **empirical study + reproducibility report**, *not* a whitepaper, and it makes **no claim of algorithmic novelty** — the algorithms are 20+ years public domain (Cormode & Muthukrishnan 2005; conservative update: Estan & Varghese 2002). The contribution is an honest, reproducible measurement of a guarantee under stress.

### What's inside (frozen scope)
- **Count-Min Sketch** + **conservative-update CMS** — from scratch, with ε/δ ↔ (width, depth) sizing and the never-undercount invariant tested.
- **Space-Saving** top-k heavy hitters (min-heap + hash index).
- **Bloom filter** — a warm-up "have I seen this flow?" gate.
- **Exact `dict`/`set` baseline** — ground truth for every accuracy/memory comparison.
- **Adversarial stream generator** — the standout: inputs designed to violate the guarantee.
- **Reproducible benchmark harness** → CSV + plots + a written empirical study.

### Verify me in 5 minutes
```bash
pip install -r requirements.txt
pytest -q            # correctness invariants (estimate never undercounts; error within εN)
make reproduce       # regenerates every figure/CSV from fixed seeds
```

### Literature (so you know I read it before I measured it)
Cormode & Muthukrishnan 2005 (CMS) · Estan & Varghese 2002 (conservative update) · Metwally et al. 2005 (Space-Saving) · and recent CU-CMS analysis: INRIA (Computer Networks), IEEE 2022, arXiv:2405.12034 (2024), ACM SIGMETRICS 2025. SketchFlow reproduces their curves, then stresses them.

---
*Built by [@neil-cipher](https://github.com/neil-cipher) · VIT Vellore CSE (Core) · Semester-1 flagship. Every commit adds a real, tested capability and a 4-line note on the concept it drills. No green-square farming.*
