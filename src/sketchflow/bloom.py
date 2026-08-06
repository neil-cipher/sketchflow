"""Bloom filter -- the warm-up sketch: "have I seen this flow before?"

A bit array + k hash functions (the step-2 fair dealers). add() sets k bits,
query checks them. One-sided error: it may say "maybe seen" for a new key
(false positive) but can NEVER say "no" for a key it has seen -- no false
negatives, by construction. Analytic false-positive rate after n inserts
into m bits with k hashes: (1 - e^{-kn/m})^k  (Bloom, CACM 1970).
"""
from sketchflow.hashing import HashFamily


class BloomFilter:
    """Fixed-memory membership sketch with one-sided error."""

    def __init__(self, m_bits=8192, k=4, seed=42):
        if m_bits < 8 or k < 1:
            raise ValueError("m_bits >= 8 and k >= 1 required")
        self.m = m_bits
        self.k = k
        self.bits = bytearray(m_bits // 8 + 1)
        self.family = HashFamily(k=k, width=m_bits, seed=seed)
        self.n_added = 0

    def add(self, key):
        for pos in self.family.buckets(key):
            self.bits[pos >> 3] |= 1 << (pos & 7)
        self.n_added += 1

    def __contains__(self, key):
        return all(self.bits[p >> 3] & (1 << (p & 7)) for p in self.family.buckets(key))

    def memory_bits(self):
        return self.m
