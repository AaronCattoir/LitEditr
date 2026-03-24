"""Diff / invalidation helpers."""

from narrative_dag.diffing import (
    affected_char_ranges_in_new,
    chunk_ids_intersecting_ranges,
    sha256_text,
)


def test_sha256_stable():
    assert len(sha256_text("hello")) == 64


def test_affected_ranges_simple_replace():
    prev = "aaabbbccc"
    new = "aaaxxxccc"
    r = affected_char_ranges_in_new(prev, new)
    assert r and r[0][0] <= 3 < r[0][1]


def test_chunk_intersection():
    chunks = [
        {"id": "c1", "start_char": 0, "end_char": 10},
        {"id": "c2", "start_char": 10, "end_char": 20},
    ]
    dirty = chunk_ids_intersecting_ranges(chunks, [(5, 15)])
    assert dirty == {"c1", "c2"}
