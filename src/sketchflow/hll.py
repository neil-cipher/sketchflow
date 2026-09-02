"""HyperLogLog -- counting DISTINCT things in one pass, in a few KB.

OPTIONAL stretch (plan.json step 27, phase P7 -- built only now that the core
is fully green and tagged ``green-sketchflow-final``). The Count-Min core
answers "how many times did key X appear?"; HyperLogLog answers a DIFFERENT
question -- "how many DISTINCT keys appeared at all?" (the cardinality of the
set) -- using memory that grows with the *log of the log* of the count, not
the count. A few kilobytes of one-byte registers estimate cardinalities into
the billions.

Primary sources (every constant below is TAKEN FROM THESE and EXPLAINED, not
copied blind -- the plan's step-27 note demands "magic constants explained not
cargo-culted"):
  * Flajolet & Martin, "Probabilistic Counting Algorithms for Data Base
    Applications", JCSS 1985 -- the leading-zero (rank) trick.
  * Flajolet, Fusy, Gandouet & Meunier, "HyperLogLog: the analysis of a
    near-optimal cardinality estimation algorithm", AofA 2007 -- the
    harmonic-mean estimator, the bias constant alpha_m, and the small-range
    (linear-counting) correction used here.

THE IDEA in one breath. Hash each key to a uniform 64-bit string. In a uniform
string the chance of starting with exactly (r-1) zeros then a one is 2^-r, so
seeing a hash that begins with a run of r zeros is evidence you have seen about
2^r distinct keys (rare patterns only surface in large sets). Track the longest
leading-zero run and you get a crude log2(cardinality). That lone estimator has
enormous variance, so HLL splits the hash: the first p bits pick one of
m = 2^p registers, each keeping the max run it has seen; averaging the m
independent estimators with a *harmonic* mean (which tames the upward outliers
a plain average would be wrecked by) yields a relative standard error of
1.04 / sqrt(m).
"""
from __future__ import annotations

import math

from sketchflow.hashing import TabulationHash

__all__ = ["HyperLogLog", "alpha_m"]

_MASK64 = (1 << 64) - 1


def alpha_m(m: int) -> float:
    """The bias-correction constant for ``m`` registers -- the one "magic
    number" in HLL, given here with its provenance instead of copied blind.

    The raw estimator ``m^2 / sum_j 2^-M[j]`` is biased HIGH: the harmonic
    mean of the register indicators systematically overshoots the true
    cardinality. Flajolet et al. (2007) derive the exact multiplicative bias
    as an integral,

        alpha_m = ( m * integral_0^inf ( log2( (2+u)/(1+u) ) )^m du )^-1 ,

    which has no tidy closed form for small m, so the paper TABULATES
    m = 16, 32, 64 and gives the large-m form 0.7213 / (1 + 1.079/m) (whose
    limit as m -> inf is 1/(2 ln 2) ~= 0.7213). The values below are exactly
    those -- nothing here is folklore.
    """
    if m < 16:
        raise ValueError(f"HLL needs m >= 16 registers, got {m}")
    if m == 16:
        return 0.673
    if m == 32:
        return 0.697
    if m == 64:
        return 0.709
    return 0.7213 / (1.0 + 1.079 / m)


class HyperLogLog:
    """Fixed-memory distinct-count (cardinality) estimator.

    ``precision`` p in [4, 18] -> m = 2^p one-byte registers. The relative
    standard error is 1.04 / sqrt(m): p = 14 (16384 registers, 16 KB) gives
    ~0.8% typical error, independent of how large the true count is.
    """

    def __init__(self, precision: int = 14, seed: int = 42):
        if not (4 <= precision <= 18):
            raise ValueError(f"precision must be in [4, 18], got {precision}")
        self.p = precision
        self.m = 1 << precision
        self.seed = seed
        self._hash = TabulationHash(seed)
        self.registers = bytearray(self.m)      # all zero == empty
        self._rest_bits = 64 - precision        # bits left after the p index bits

    def add(self, key) -> None:
        """Fold one key into the sketch. Idempotent in effect: re-adding a key
        can only leave a register unchanged (its run is a max), so duplicates
        never inflate the estimate."""
        h = self._hash(key) & _MASK64
        idx = h >> self._rest_bits                       # top p bits -> register
        rest = h & ((1 << self._rest_bits) - 1)          # remaining bits -> the run
        # rank = position of the leftmost 1-bit in the rest field, counting
        # from the MSB side = (leading zeros) + 1. bit_length() gives the
        # position of the highest set bit; rest == 0 (no set bit) yields the
        # maximal run rest_bits + 1, which this formula produces cleanly.
        rank = self._rest_bits - rest.bit_length() + 1
        if rank > self.registers[idx]:
            self.registers[idx] = rank

    def cardinality(self) -> float:
        """Estimate the number of DISTINCT keys added.

        Raw HLL estimate  E = alpha_m * m^2 / sum_j 2^-M[j], then the
        small-range fix: when E is small (<= 2.5 m) and some registers are
        still empty, the harmonic estimator is unreliable, so fall back to
        *linear counting* -- V empty registers out of m implies, by the
        balls-in-bins expectation m*(1 - 1/m)^n ~= m*e^{-n/m}, a count of
        m * ln(m / V).

        NO large-range correction is included, on purpose. The classic one
        (E > 2^32/30  ->  E = -2^32 * ln(1 - E/2^32)) exists only to undo
        32-bit hash SATURATION -- distinct values approaching 2^32 start
        colliding and the register runs stop growing. This module hashes to
        64 bits, moving that wall past 10^19, far beyond any cardinality
        these registers can represent, so bolting on the 2^32 correction
        would be exactly the cargo-culting the step forbids.
        """
        m = self.m
        inv_sum = 0.0
        zeros = 0
        for r in self.registers:
            inv_sum += 1.0 / (1 << r)   # 2^-M[j]; an empty register (r==0) adds 1.0
            if r == 0:
                zeros += 1
        raw = alpha_m(m) * m * m / inv_sum
        if raw <= 2.5 * m and zeros > 0:
            return m * math.log(m / zeros)   # linear counting for small sets
        return raw

    def __len__(self) -> int:
        return round(self.cardinality())

    def merge(self, other: "HyperLogLog") -> "HyperLogLog":
        """Union two sketches register-wise (take the max of each register).

        Valid ONLY when both were built with the same precision AND seed --
        otherwise their registers index different hash partitions and the
        merge is meaningless. Returns a NEW sketch estimating |A union B|;
        neither input is mutated. This is why sketches "compose": the union
        of the sets maps to the elementwise max of the registers.
        """
        if self.p != other.p or self.seed != other.seed:
            raise ValueError("merge requires identical precision and seed")
        out = HyperLogLog(precision=self.p, seed=self.seed)
        out.registers = bytearray(
            max(a, b) for a, b in zip(self.registers, other.registers)
        )
        return out

    def memory_bytes(self) -> int:
        """Register footprint: one byte per register. A run never exceeds
        64 - p + 1 (<= 61), comfortably inside a single byte."""
        return self.m
