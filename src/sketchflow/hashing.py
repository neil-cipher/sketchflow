"""The hash toolkit -- the "fair dealers" every sketch depends on.

Step 2: k independent, seedable hash functions mapping any key to a table
column in [0, width). The Count-Min Sketch's e/d promise silently assumes
these spread keys evenly and independently -- so we test that FIRST.

Method: simple tabulation hashing (Zobrist 1970; analysed by Patrascu &
Thorup, "The Power of Simple Tabulation Hashing", J.ACM 2012): XOR of
per-byte random tables. Fast, seedable, and provably close to truly
random for exactly the uses a sketch needs.
"""
import random

_MASK64 = (1 << 64) - 1


class TabulationHash:
    """One seeded tabulation hash: bytes in -> 64-bit mix out."""

    def __init__(self, seed):
        rng = random.Random(seed)
        self.tables = [[rng.getrandbits(64) for _ in range(256)] for _ in range(8)]

    def __call__(self, key):
        data = key if isinstance(key, bytes) else str(key).encode("utf-8")
        h = 0
        for i, b in enumerate(data):
            h ^= self.tables[i % 8][b]
            h = ((h << 7) | (h >> 57)) & _MASK64  # rotate so long keys keep mixing
        return h


class HashFamily:
    """k independent hash functions, all seedable, mapping keys to [0, width)."""

    def __init__(self, k, width, seed=42):
        if k < 1 or width < 1:
            raise ValueError("k and width must be >= 1")
        self.k = k
        self.width = width
        self.funcs = [TabulationHash(seed * 1_000_003 + i) for i in range(k)]

    def bucket(self, i, key):
        return self.funcs[i](key) % self.width

    def buckets(self, key):
        return [f(key) % self.width for f in self.funcs]
