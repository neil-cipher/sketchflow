# Ishan CSE-Core Projects — GROUNDED TRUTH & ANTI-DRIFT CONSTITUTION
**Non-negotiable. Every daily project run reads and obeys this BEFORE writing a single line of code.**
Owner: Suds · Subject: Ishan Neil Bhargav · GitHub: `neil-cipher` · Started: 26-Jul-2026

---

## The exact failure this file exists to prevent
A fresh session on **day 6** (or day 26) has **zero memory** of days 1–5. If it rebuilds state from prose, from a summary, or from its own recall, it will: hallucinate what code exists, rebuild phantom functions, contradict a decision made on day 2, or claim a benchmark that was never run — and **every real commit since then is poisoned or wasted.** These ten rules make that structurally impossible. Drift is treated as a P0 bug, not a stylistic slip.

---

## Rule 0 — THE REPO IS THE ONLY SOURCE OF TRUTH. Prose is never trusted.
Every run begins by reading **reality**, never memory:
1. `git pull` the project repo.
2. Read the actual files at `HEAD`.
3. Run the actual test suite.
4. Read `.project-meta/ledger.json`.

Then **RECONCILE**: if the ledger disagrees with the code, **the CODE WINS.** Patch the ledger to match reality, log the discrepancy in `decisions.log`, and only then proceed. A run may never build on anything not present at `HEAD` and green in tests.

## Rule 1 — Frozen spec, immutable plan.
`.project-meta/spec.md` (the frozen brief) and `.project-meta/plan.json` (the ordered step list) are written **once** at project selection and are **read-only** for every daily run. A run may advance the step pointer or raise a blocker; it may **not** redefine the project, re-order the plan, or invent steps. Scope drift = bug.

## Rule 2 — A step is "done" ONLY if a verifiable artifact proves it.
Not because the ledger says so. **Done = a commit SHA exists AND its tests are green in CI AND the file/function it claims to add is present at HEAD.** Status is *derived* from `git log` + CI on every run, never asserted from memory.

## Rule 3 — Cold-start recovery protocol (top of every run, no exceptions).
`pull → read code → run tests → diff(actual, ledger) → on mismatch: trust the repo, correct the ledger, log it → only then proceed.` If tests are **RED on arrival**, the run's ONLY job is to get back to green (or roll to the last green tag). It may **never** add a new feature on top of a broken base.

## Rule 4 — Invariants gate every commit. Any failure = DIE, do not push.
Before any commit, all must hold:
- **No regression** — every prior test still passes.
- **Builds clean** — new code imports/compiles.
- **Claim is sourced** — the day's factual claim (novelty / benchmark / "state-of-the-art") carries a primary-source citation, skeptic-checked exactly like the SAP sprint.
- **Author is `neil-cipher`.**
If any fails → stop, write the reason to the page's "⏳ needs you / blocked" strip, **do not push.** A broken push poisons tomorrow.

## Rule 5 — Two-tier, self-describing storage (no single point of failure).
- **CANONICAL:** `.project-meta/` inside the repo (`ledger.json`, `spec.md`, `plan.json`, `decisions.log`) — committed alongside the code, so the repo *describes itself* and travels with its own truth.
- **MIRROR:** `C:\...\19. VITEEE\Info\PROJECTS\` on OneDrive — a synced copy so the job can read state even before touching git, and survive a reclaimed cloud container.
- **On conflict, the REPO wins** (it is version-controlled and artifact-backed; the mirror can go stale).

## Rule 6 — Checkpoint tags + rollback, so "N days wasted" cannot happen.
Every ~7 green steps, tag `green-<project>-<n>`. If drift/corruption/red-on-arrival cannot be cleanly fixed, **roll back to the last green tag.** Worst case is losing days-since-last-tag, never the whole project.

## Rule 7 — No forward references, no phantom builds.
A step may only call functions / import modules / read files that **actually exist at HEAD** (verified this run). Never build on something a note merely *said* was done.

## Rule 8 — Human-in-loop is a STATE, not an error.
Captcha / OAuth click / Kaggle-or-dataset accept / first `git push` / any credential wall → write the exact step to the page's "⏳ needs you" strip and **DIE.** The next run resumes from the recorded step once the human marks it done. Never fake, skip, or guess past a human step.

## Rule 9 — Idempotent daily writes.
Page edits are marker-bounded; ledger updates are keyed by step id. Re-running a day yields the same result — no append-duplication, no double-commit.

## Rule 10 — Factual & pedagogical bar ≥ the IITK evidence.
Every project claim is verified to a primary source before it reaches the page, a README, or a commit message. Standard: **"a FAANG/Marquee reviewer AND an MS admissions committee can both independently verify it."** Each step also ships a 4-line layman note (what / why / concept it drills / what's next) — teaching Ishan to run the next project himself is as mandatory as the code. Better than the IITK packet, never worse.

---

### Enforcement summary (the daily run literally checks these in order)
`0` read reality → `3` reconcile & recover → (do one step) → `7` no phantom deps → `2` artifact-backed → `4` invariants or DIE → `6` tag if checkpoint → `8` human-block? die politely → `9` idempotent page+ledger write → commit as `neil-cipher` → chain tomorrow.

**If a run cannot satisfy Rule 0 (repo unreachable) or Rule 4 (invariants fail), it does NOTHING except report and die. A silent, drifting, or hallucinated commit is worse than a skipped day.**
