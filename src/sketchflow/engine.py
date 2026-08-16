"""SketchFlow engine — CMS + Space-Saving in one streaming pass.

Combines a Count-Min Sketch (or its conservative-update variant) for
frequency estimation with a Space-Saving tracker for heavy hitter
detection. Feed items once; ask "how many?" (CMS) and "who's on top?"
(Space-Saving) from the same ingestion.

**Step 12** of plan.json — the composing step that turns individual
data structures into an analytics engine.

Usage::

    from sketchflow.engine import SketchEngine

    engine = SketchEngine(epsilon=0.001, delta=0.01, top_k=20)
    for item in stream:
        engine.add(item)

    # Frequency estimate for a specific key
    engine.estimate(key)

    # Top-k heavy hitters with CMS-estimated counts
    engine.heavy_hitters()

    # Summary statistics
    engine.summary()

The engine auto-sizes the CMS from (ε, δ) via ``size_cms()``, so the
caller specifies the *accuracy guarantee* they want, not raw dimensions.

Reference: this is the standard "sketch engine" pattern found in
production stream-processing systems — a frequency sketch plus a
top-k tracker, fed in parallel from a single stream.
"""

from __future__ import annotations

from sketchflow.cms import CountMinSketch, size_cms
from sketchflow.cu_cms import ConservativeUpdateCMS
from sketchflow.space_saving import SpaceSaving

__all__ = ["SketchEngine"]


class SketchEngine:
    """Combined CMS + Space-Saving streaming analytics engine.

    Parameters
    ----------
    epsilon : float
        CMS additive error fraction, in (0, 1).  Smaller ε → wider
        CMS → tighter frequency estimates → more memory.
    delta : float
        CMS failure probability, in (0, 1).  Smaller δ → deeper CMS
        → more hash rows → higher success probability.
    top_k : int
        Number of heavy hitter slots for Space-Saving.  Must be >= 1.
    seed : int
        Hash family seed for reproducibility.
    conservative : bool
        If True, use ConservativeUpdateCMS instead of plain CMS.
        CU reduces overestimation without changing the guarantee.

    Attributes
    ----------
    cms : CountMinSketch or ConservativeUpdateCMS
        The frequency sketch.
    tracker : SpaceSaving
        The heavy hitter tracker.
    total : int
        Total items ingested (stream length N).
    """

    def __init__(
        self,
        epsilon: float = 0.001,
        delta: float = 0.01,
        top_k: int = 20,
        seed: int = 42,
        conservative: bool = False,
    ):
        if top_k < 1:
            raise ValueError(f"top_k must be >= 1, got {top_k}")

        width, depth = size_cms(epsilon, delta)
        self.epsilon = epsilon
        self.delta = delta
        self._top_k = top_k
        self.seed = seed
        self.conservative = conservative

        cls = ConservativeUpdateCMS if conservative else CountMinSketch
        self.cms = cls(width=width, depth=depth, seed=seed)
        self.tracker = SpaceSaving(k=top_k)

    @property
    def total(self) -> int:
        """Stream length N — kept in sync across both structures."""
        return self.cms.total

    def add(self, key: str, count: int = 1) -> None:
        """Ingest one occurrence (or ``count``) of ``key`` into both
        the CMS and the Space-Saving tracker in a single call."""
        self.cms.add(key, count=count)
        self.tracker.add(key, count=count)

    def estimate(self, key: str) -> int:
        """CMS frequency estimate for ``key``.

        Returns the min-over-rows estimate from the underlying CMS.
        Guaranteed to be >= true count and <= true count + ε·N with
        probability >= 1 − δ.
        """
        return self.cms.query(key)

    def heavy_hitters(self, n: int | None = None) -> list[tuple[str, int]]:
        """Top-k heavy hitters with CMS-estimated counts.

        Space-Saving identifies *which* keys are heavy; the CMS provides
        more accurate frequency estimates (especially with conservative
        update).  This method returns the Space-Saving top-k keys but
        replaces the Space-Saving count estimates with the CMS estimates,
        which are tighter.

        Parameters
        ----------
        n : int or None
            How many to return.  If None, returns all monitored keys
            (up to ``top_k``).  If given, returns at most ``n``.

        Returns
        -------
        list of (key, cms_estimate) tuples, sorted by CMS estimate
        descending.  Ties are broken alphabetically by key.
        """
        # Get the keys from Space-Saving (it knows WHO is heavy)
        ss_top = self.tracker.top_k(n=n)
        # Re-estimate counts via CMS (it knows HOW MANY, more accurately)
        cms_estimated = [(key, self.cms.query(key)) for key, _ in ss_top]
        # Re-sort by CMS estimate (may differ slightly from SS ordering)
        cms_estimated.sort(key=lambda kv: (-kv[1], kv[0]))
        return cms_estimated

    def summary(self) -> dict:
        """Engine summary: config, stream length, top heavy hitters.

        Returns a dict suitable for quick inspection or logging.
        """
        return {
            "epsilon": self.epsilon,
            "delta": self.delta,
            "cms_width": self.cms.width,
            "cms_depth": self.cms.depth,
            "top_k": self._top_k,
            "conservative": self.conservative,
            "total": self.total,
            "heavy_hitters": self.heavy_hitters(),
        }
