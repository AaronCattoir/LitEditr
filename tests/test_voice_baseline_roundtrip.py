"""Voice baseline persistence and API serialization."""

from __future__ import annotations

import pytest

from narrative_dag.db import init_db
from narrative_dag.schemas import DocumentState, VoiceLayer, VoiceProfile
from narrative_dag.store.run_store import RunStore, serialize_story_wide_for_api


@pytest.fixture
def run_store():
    conn = init_db(":memory:")
    try:
        yield RunStore(conn)
    finally:
        conn.close()


def test_save_load_document_state_voice_baseline_roundtrip(run_store: RunStore):
    vb = VoiceProfile(
        lexical=VoiceLayer(summary="Lean diction.", observations=["Concrete verbs"]),
        syntactic=VoiceLayer(summary="Short sentences dominate.", observations=[]),
        rhetorical=VoiceLayer(summary="Understated irony.", observations=["Dry humor"]),
        psychological=VoiceLayer(summary="Close third withheld affect.", observations=[]),
    )
    ds = DocumentState(voice_baseline=vb)
    run_id = "test-run-voice-1"
    run_store.save_run_meta(run_id, document_id="d1", revision_id="r1")
    run_store.save_document_state(run_id, ds)
    loaded = run_store.get_document_state(run_id)
    assert loaded is not None
    assert isinstance(loaded.voice_baseline, VoiceProfile)
    assert loaded.voice_baseline.lexical.summary == "Lean diction."
    assert loaded.voice_baseline.lexical.observations == ["Concrete verbs"]
    assert loaded.voice_baseline.rhetorical.observations == ["Dry humor"]


def test_serialize_story_wide_includes_voice_baseline(run_store: RunStore):
    vb = VoiceProfile(
        lexical=VoiceLayer(summary="Summary here", observations=["obs1"]),
        syntactic=VoiceLayer(summary="", observations=[]),
        rhetorical=VoiceLayer(summary="", observations=[]),
        psychological=VoiceLayer(summary="", observations=[]),
    )
    ds = DocumentState(voice_baseline=vb)
    sw = serialize_story_wide_for_api(ds)
    assert sw["voice_baseline"] is not None
    assert sw["voice_baseline"]["lexical"]["summary"] == "Summary here"
    assert sw["voice_baseline"]["lexical"]["observations"] == ["obs1"]
