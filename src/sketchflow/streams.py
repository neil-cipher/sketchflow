"""Stream sources for SketchFlow.

Step 1: a seeded synthetic Zipfian stream -- traffic-like data whose true
answer can always be recomputed exactly. Real trace loaders (CIC-IDS, MAWI)
arrive in later steps per .project-meta/plan.json.
"""
import bisect
import random


def zipfian_stream(n_items=10_000, universe=1_000, alpha=1.2, seed=42):
    """Yield n_items keys drawn from a Zipf-like (heavy-tail) distribution.

    Why Zipf? Real network traffic is heavy-tailed: a few "elephant" flows
    dominate while most flows are tiny "mice". Zipf(alpha) reproduces that
    shape. Seeded -> the exact same stream can be regenerated, so every
    sketch built later can be graded against known ground truth.
    """
    if n_items < 0 or universe < 1:
        raise ValueError("n_items must be >= 0 and universe >= 1")
    rng = random.Random(seed)
    weights = [1.0 / (rank ** alpha) for rank in range(1, universe + 1)]
    total = sum(weights)
    cum = []
    acc = 0.0
    for w in weights:
        acc += w / total
        cum.append(acc)
    cum[-1] = 1.0  # guard against float round-off
    for _ in range(n_items):
        idx = bisect.bisect_left(cum, rng.random())
        yield f"item-{idx}"
