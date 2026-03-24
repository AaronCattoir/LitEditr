"""Tests for detection layer."""

from __future__ import annotations

import pytest
from narrative_dag.nodes.detection import (
    drift_detector,
    cliche_detector,
    vagueness_detector,
    run_all_detectors,
)
from narrative_dag.schemas import Chunk, ContextWindow


@pytest.fixture
def state_with_context():
    chunks = [
        Chunk(
            id="c1",
            text="At the end of the day, something happened. Things were vague.",
            position=0,
            start_char=0,
            end_char=len("At the end of the day, something happened. Things were vague."),
        )
    ]
    ctx = ContextWindow(target_chunk=chunks[0], previous_chunks=[], next_chunks=[], global_summary="")
    return {"context_window": ctx, "document_state": None}


def test_drift_detector(state_with_context):
    out = drift_detector(state_with_context)
    assert "drift_result" in out
    assert 0 <= out["drift_result"].drift_score <= 1


def test_cliche_detector(state_with_context):
    out = cliche_detector(state_with_context)
    assert "cliche_result" in out
    assert "at the end of the day" in [f.lower() for f in out["cliche_result"].cliche_flags] or len(out["cliche_result"].cliche_flags) >= 0


def test_vagueness_detector(state_with_context):
    out = vagueness_detector(state_with_context)
    assert "vagueness_result" in out
    assert out["vagueness_result"].impact in ("low", "medium", "high")


def test_run_all_detectors(state_with_context):
    out = run_all_detectors(state_with_context)
    assert "drift_result" in out
    assert "cliche_result" in out
    assert "vagueness_result" in out
    assert "emotional_honesty_result" in out
    assert "redundancy_result" in out
    assert "risk_result" in out
