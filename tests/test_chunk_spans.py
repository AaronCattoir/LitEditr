"""Client chunk span validation."""

from __future__ import annotations

import pytest

from narrative_dag.chunk_spans import validate_and_build_chunks_from_spans


def test_partition_full_document():
    text = "Hello world"
    chunks = validate_and_build_chunks_from_spans(
        text,
        [("c1", 0, 5), ("c2", 5, 11)],
    )
    assert len(chunks) == 2
    assert chunks[0].text == "Hello"
    assert chunks[1].text == " world"


def test_gap_raises():
    with pytest.raises(ValueError, match="contiguously"):
        validate_and_build_chunks_from_spans("abc", [("a", 0, 1), ("b", 2, 3)])


def test_overlap_raises():
    with pytest.raises(ValueError, match="contiguously"):
        validate_and_build_chunks_from_spans("ab", [("a", 0, 2), ("b", 1, 2)])


def test_incomplete_coverage_raises():
    with pytest.raises(ValueError, match="full document"):
        validate_and_build_chunks_from_spans("abc", [("a", 0, 1)])


def test_duplicate_chunk_id_raises():
    with pytest.raises(ValueError, match="duplicate"):
        validate_and_build_chunks_from_spans("ab", [("x", 0, 1), ("x", 1, 2)])


def test_emoji_partitions_by_codepoint_not_utf16():
    """JS String.length counts UTF-16; Python len(str) counts code points — spans must match Python."""
    text = "ab😀cd"
    chunks = validate_and_build_chunks_from_spans(
        text,
        [("c1", 0, 2), ("c2", 2, 3), ("c3", 3, 5)],
    )
    assert chunks[0].text == "ab"
    assert chunks[1].text == "😀"
    assert chunks[2].text == "cd"
