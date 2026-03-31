"""Tests for representation layer."""

from __future__ import annotations

import pytest
from narrative_dag.schemas import Chunk, ContextWindow, DocumentState, GenreIntention, VoiceLayer, VoiceProfile
from narrative_dag.nodes.ingestion import chunk_document, build_context_window
from narrative_dag.nodes.representation import paragraph_analyzer, voice_profiler, run_document_state_builder


@pytest.fixture
def state_with_context(sample_document, genre_intention):
    chunks = chunk_document(sample_document)
    ctx = build_context_window(chunks, "c1", window_size=2)
    return {
        "chunks": chunks,
        "context_window": ctx,
        "genre_intention": genre_intention,
        "global_summary": "",
    }


def test_paragraph_analyzer(state_with_context):
    out = paragraph_analyzer(state_with_context)
    assert "paragraph_analysis" in out
    pa = out["paragraph_analysis"]
    assert pa.function in ("narration", "dialogue", "transition")
    assert pa.intent


def test_voice_profiler(state_with_context):
    state_with_context.update(paragraph_analyzer(state_with_context))
    out = voice_profiler(state_with_context)
    assert "voice_profile" in out
    vp = out["voice_profile"]
    assert vp.lexical.summary or vp.lexical.observations


def test_document_state_builder(state_with_context):
    state_with_context.update(paragraph_analyzer(state_with_context))
    state_with_context.update(voice_profiler(state_with_context))
    out = run_document_state_builder(state_with_context)
    assert "document_state" in out
    assert out["document_state"].allowed_variance.bounds


def test_document_state_builder_keeps_prior_voice_when_current_empty(state_with_context):
    state_with_context["document_state"] = DocumentState(
        voice_baseline=VoiceProfile(
            lexical=VoiceLayer(summary="Prior baseline summary", observations=["kept"]),
        ),
    )
    state_with_context.update(paragraph_analyzer(state_with_context))
    state_with_context["voice_profile"] = VoiceProfile()
    out = run_document_state_builder(state_with_context)
    vb = out["document_state"].voice_baseline
    assert isinstance(vb, VoiceProfile)
    assert vb.lexical.summary == "Prior baseline summary"
    assert "kept" in vb.lexical.observations


def test_document_state_builder_extends_prior_document_state(state_with_context):
    state_with_context.update(paragraph_analyzer(state_with_context))
    state_with_context.update(voice_profiler(state_with_context))
    state_with_context["document_state"] = DocumentState(
        emotional_curve=[{"chunk_id": "c0", "register": "uneasy"}],
        narrative_map=[{"chunk_id": "c0", "intent": "setup"}],
        character_voice_map={"Wayne": {"register": "loose"}},
    )

    out = run_document_state_builder(state_with_context)

    doc_state = out["document_state"]
    assert doc_state.emotional_curve[0]["chunk_id"] == "c0"
    assert any(entry["chunk_id"] == "c1" for entry in doc_state.narrative_map)
    assert doc_state.character_voice_map["Wayne"]["register"] == "loose"


def test_document_state_builder_replaces_existing_chunk_entries(state_with_context):
    state_with_context["current_chunk_id"] = "c1"
    state_with_context.update(paragraph_analyzer(state_with_context))
    state_with_context.update(voice_profiler(state_with_context))
    state_with_context["document_state"] = DocumentState(
        emotional_curve=[{"chunk_id": "c1", "register": "old"}],
        narrative_map=[{"chunk_id": "c1", "intent": "old-intent"}],
    )

    out = run_document_state_builder(state_with_context)
    doc_state = out["document_state"]

    curve_for_c1 = [e for e in doc_state.emotional_curve if e.get("chunk_id") == "c1"]
    narrative_for_c1 = [e for e in doc_state.narrative_map if e.get("chunk_id") == "c1"]

    assert len(curve_for_c1) == 1
    assert len(narrative_for_c1) == 1
    assert curve_for_c1[0]["register"] != "old"
    assert narrative_for_c1[0]["intent"] != "old-intent"
