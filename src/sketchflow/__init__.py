"""SketchFlow — a Count-Min Sketch you can break.

A from-scratch sublinear stream-counting engine. This package is built ONE
tested step at a time per .project-meta/plan.json (immutable). Modules land in
plan order: hashing -> bloom -> count_min -> cu_count_min -> space_saving ->
baseline -> streams -> adversary -> bench.
"""
__version__ = "0.1.0"
__author__ = "neil-cipher"
