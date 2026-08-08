"""Bloom filter sizing calculator.

Given how many items you expect (n) and how much error you can live
with (target false-positive rate p), compute the table size m (bits)
and the number of hash functions k by the standard closed forms:

    m = ceil( -n * ln(p) / (ln 2)^2 )
    k = max(1, round( (m / n) * ln 2 ))

Derivation: the analytic FPR of a Bloom filter is (1 - e^{-kn/m})^k
(Bloom, CACM 1970). Minimising it over k for fixed m/n gives
k* = (m/n) ln 2, and plugging back in gives the m formula for a
target p. This is the first hands-on feel of *buying accuracy with
memory*: halving p costs a fixed number of extra bits per item
(~1.44 bits per halving).
"""

from __future__ import annotations

import math

__all__ = ["size_bloom", "analytic_fpr"]


def size_bloom(n: int, target_fpr: float) -> tuple[int, int]:
    """Return (m_bits, k) sized so a Bloom filter holding ``n`` items
    has analytic false-positive rate <= ``target_fpr``.

    n must be >= 1; target_fpr must be in (0, 1).
    """
    if n < 1:
        raise ValueError(f"n must be >= 1, got {n}")
    if not (0.0 < target_fpr < 1.0):
        raise ValueError(f"target_fpr must be in (0, 1), got {target_fpr}")

    ln2 = math.log(2.0)
    m = math.ceil(-(n * math.log(target_fpr)) / (ln2 * ln2))

    def best_k(m_bits: int) -> int:
        # k must be an integer, so try floor and ceil of the optimum
        # and keep whichever gives the lower analytic FPR.
        k_opt = (m_bits / n) * ln2
        candidates = {max(1, math.floor(k_opt)), max(1, math.ceil(k_opt))}
        return min(candidates, key=lambda k: analytic_fpr(m_bits, k, n))

    # Rounding k to an integer can leave the analytic FPR a hair ABOVE
    # the target (e.g. n=10k, p=1% -> 0.01004). A sizing calculator that
    # misses its own promise is useless, so grow m (a fraction of a
    # percent) until the promise holds exactly.
    k = best_k(m)
    while analytic_fpr(m, k, n) > target_fpr:
        m = math.ceil(m * 1.001)
        k = best_k(m)
    return m, k


def analytic_fpr(m: int, k: int, n: int) -> float:
    """Textbook false-positive probability (1 - e^{-kn/m})^k."""
    if m < 1 or k < 1 or n < 0:
        raise ValueError("m>=1, k>=1, n>=0 required")
    return (1.0 - math.exp(-k * n / m)) ** k
