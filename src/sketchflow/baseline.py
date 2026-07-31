"""Exact baseline counter -- the ground truth every sketch is graded against."""


class ExactCounter:
    """Counts every key exactly using a plain dict.

    This is the memory-hungry "obvious way". It is kept forever as the
    referee: every sketch's estimate in later steps is compared against
    these true counts, and its memory use against this dict's size.
    """

    def __init__(self):
        self.counts = {}
        self.total = 0

    def add(self, key, count=1):
        self.counts[key] = self.counts.get(key, 0) + count
        self.total += count

    def query(self, key):
        return self.counts.get(key, 0)

    def top_k(self, k):
        return sorted(self.counts.items(), key=lambda kv: (-kv[1], kv[0]))[:k]

    def distinct_keys(self):
        return len(self.counts)
