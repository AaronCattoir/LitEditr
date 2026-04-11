"""Tests for Pydantic schemas."""

from __future__ import annotations

import pytest
from narrative_dag.schemas import (
    Chunk,
    ContextWindow,
    DialecticMediationResult,
    DialecticSynthesisResult,
    DriftResult,
    EditorJudgment,
    GenreIntention,
    RawDocument,
)


def test_chunk_deterministic_id():
    c = Chunk(id="c1", text="Hello.", position=0, start_char=0, end_char=len("Hello."))
    assert c.id == "c1"
    assert c.position == 0


def test_genre_intention():
    g = GenreIntention(genre="thriller", subgenre_tags=["noir"])
    assert g.genre == "thriller"
    assert "noir" in g.subgenre_tags


def test_editor_judgment_keep():
    j = EditorJudgment(decision="keep", severity=0.2, reasoning="Fine.", core_issue="", guidance="", is_drift=False)
    assert j.decision == "keep"


def test_context_window():
    target = Chunk(id="c2", text="Mid.", position=1, start_char=0, end_char=len("Mid."))
    prev = Chunk(id="c1", text="First.", position=0, start_char=0, end_char=len("First."))
    ctx = ContextWindow(target_chunk=target, previous_chunks=[prev], next_chunks=[], global_summary="")
    assert ctx.target_chunk.id == "c2"
    assert len(ctx.previous_chunks) == 1


def test_dialectic_models_round_trip():
    m = DialecticMediationResult(
        strongest_points="a",
        contradictions="b",
        assumptions_and_values="c",
        limitations="d",
        core_tension_summary="e",
    )
    d = m.model_dump()
    assert DialecticMediationResult.model_validate(d).core_tension_summary == "e"
    s = DialecticSynthesisResult(
        integrated_perspective="1",
        resolved_contradictions="2",
        transcendence_notes="3",
        higher_level_truth="4",
    )
    assert DialecticSynthesisResult.model_validate(s.model_dump()).higher_level_truth == "4"


def test_drift_result_normalizes_paraphrased_drift_type():
    d = DriftResult.model_validate(
        {"drift_score": 0.4, "drift_type": "narrative architecture", "evidence": "x", "confidence": 0.8}
    )
    assert d.drift_type == "narrative"
