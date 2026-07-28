# SketchFlow — THE EXPLAINER (grounding file the daily job always reads)
**Purpose:** turn the daily code into a story a *first-week CSE student* understands AND a recruiter/interviewer is impressed by. This file is the source of truth for the **📖 Explainer tab** on Ishan's Projects page. Every daily run reads this, then APPENDS exactly one date-stamped step-explainer into the page's `EXPLAINER` markers — layman, low-cognitive-load, no bloat — so that by Year-3, Ishan can walk any interviewer through the whole project from memory. **Goal: internship shortlisting + placement interviews, evidenced from Day 1.**

---

## A. THE STUMBLE STORY (natural, flowing — the "how it started", stays at the top of the tab)
> Ishan didn't come to CS through a textbook. He came through **taking things apart to see why they work, then why they break** — port scanners, packet captures, a little brute-force-detector he wrote for the IIT-K packet. (That's the repo already in his Evidence tab.)
>
> One evening, staring at a capture with *millions* of packets, he asked a simple question: *"How many times did this one IP show up?"* The obvious answer — keep a giant dictionary counting every address — worked on his laptop for a small file and then fell over on a big one: too much memory. He'd hit the wall every network engineer hits.
>
> Digging for why, he found a quietly beautiful idea from 2005 called the **Count-Min Sketch**: a tiny fixed-size table that can *estimate* how often things appear, using a sliver of the memory — by being willing to be a little bit wrong, in a controlled way. It even comes with a *mathematical promise* about how wrong it can be.
>
> And that's where the competitive-programmer in him woke up. Not "cool, I'll use it" — but **"can I break its promise?"** What if I *design* the nastiest possible stream of packets on purpose? Where does the guarantee hold, and where does it crack?
>
> That question — *a Count-Min Sketch I tried to break* — became **SketchFlow**. It's the same thing he's always done (watch a stream, find what matters, see why it breaks), just levelled up from scripts to real data-structures-and-algorithms. It plugs straight into his cyber past and points straight at the DSA-heavy internships he wants.

## B. WHY THIS PROJECT (the shortlisting imperatives — a short honest story, sits under the stumble story)
A project earns an interview when it does five things. SketchFlow was chosen because it does all five, and most student projects do none:
1. **One thing, deep — not a tutorial tour.** Thousands of students have a repo that implements four textbook structures and stops. SketchFlow takes *one* (Count-Min Sketch) and pushes it past the textbook into a real finding. Depth is what a reviewer remembers.
2. **A measurable result.** Not "I built X" but "here are the accuracy-vs-memory curves, and here's the exact input where the ε/δ guarantee breaks." A number beats an adjective.
3. **Real data.** Synthetic first (so the answer is checkable), then real backbone-network traces. "Tested on real traffic" is a different sentence from "tested on my laptop."
4. **Honest framing.** It's called an *empirical study*, not a "whitepaper"; it claims **no** novelty it can't defend. A sharp interviewer trusts the whole repo more because it doesn't oversell.
5. **A coherent personal story.** It *bridges his past into his future* — packets/cyber → hard DSA. A recruiter can retell it in one line, which is exactly what gets a résumé shortlisted.
> The blunt test each choice must pass: **"Would a FAANG/Marquee reviewer AND an MS committee both independently verify this from the repo alone?"** If not, it doesn't ship.

## C. THE PER-STEP EXPLAINER FORMAT (the daily job appends ONE of these per completed step)
Each committed step becomes ONE collapsible, newest at the TOP of the step list, formatted for **zero cognitive load**:

`<details><summary>Step N · <plain-title> · <DD-Mon-YYYY></summary>`
- **In plain words:** what got built today, explained like to a smart friend who codes a little (1–2 sentences, no jargon; if a term is unavoidable, define it in 4 words).
- **Why it matters:** the real-world point — where this shows up in actual systems (1 sentence).
- **The CS concept it drills → interview-ready:** name the concept, then the **exact interview question this prepares him to answer** ("Q: *why is a hashmap O(1) average but O(n) worst?*") + a one-line answer he can say out loud.
- **What's next:** the single next step (1 line), so the story flows.
- **🎤 Say-it-out-loud soundbite:** one confident sentence he could drop in an interview about today's piece.

Rules: **succinct, never bloated.** No step-explainer exceeds ~90 words. British-simple language. Tie back to the stumble story or his Evidence projects whenever it's natural (e.g. "same idea as the brute-force counter in his IIT-K repo, but now with a proven error bound"). Date-stamp every step. Never leave a completed code-step without its explainer — the teaching is as mandatory as the code (Rule 10).

## D. INTERVIEW PREP INDEX (the job maintains this list as concepts are covered — one line each)
As steps land, keep a running "you can now answer these" list at the bottom of the tab, e.g.:
- Hashing & collisions — *why average O(1), worst O(n)*
- Big-O / space–time trade-offs — *why trade accuracy for memory*
- Probabilistic data structures — *what a Count-Min Sketch is, in 20 seconds*
- The ε/δ guarantee — *what the promise means and when it breaks*
- Heavy hitters / top-k — *how Space-Saving finds the biggest flows in bounded memory*
- Benchmarking & reproducibility — *how he proved the result, not just claimed it*

**The daily job MUST:** read this file → pick the format in §C → append one dated step-explainer (newest on top) into the page `EXPLAINER` markers → add any new concept to §D's on-page index → keep the stumble (§A) and why-this (§B) stories pinned at the top, unchanged unless the project's framing genuinely changes.
