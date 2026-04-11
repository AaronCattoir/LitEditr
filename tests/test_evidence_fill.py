"""Tests for evidence span normalization and inference."""

from narrative_dag.evidence_fill import _normalize_spans_against_chunk
from narrative_dag.schemas import EvidenceSpan


def test_normalize_spans_clamps_to_chunk():
    spans = [
        EvidenceSpan(start_char=0, end_char=5, quote="x", label="a"),
        EvidenceSpan(start_char=100, end_char=200, quote="y", label="b"),
    ]
    out = _normalize_spans_against_chunk(spans, chunk_start=50, chunk_end=120, chunk_text="x" * 70)
    assert len(out) == 1
    assert out[0].start_char == 100
    assert out[0].end_char == 120


def test_normalize_spans_drops_invalid():
    spans = [
        EvidenceSpan(start_char=10, end_char=10, quote="", label=""),
        EvidenceSpan(start_char=20, end_char=15, quote="", label=""),
    ]
    assert _normalize_spans_against_chunk(spans, 0, 100, "x" * 100) == []
