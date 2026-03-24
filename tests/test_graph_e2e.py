"""End-to-end test: run_analysis produces report and deterministic chunks."""

from __future__ import annotations

import pytest
from narrative_dag.schemas import GenreIntention, RawDocument
from narrative_dag.graph import run_analysis


def test_run_analysis_produces_report():
    doc = RawDocument(text="Para one.\n\nPara two.\n\nPara three.")
    genre = GenreIntention(genre="literary_fiction")
    state, chunk_judgments = run_analysis(doc, genre, "test-run-1")
    assert state["chunks"]
    assert len(chunk_judgments) == len(state["chunks"])
    assert state.get("editorial_report")
    assert state["editorial_report"].run_id == "test-run-1"
    assert state.get("document_state") is not None
    assert state["document_state"].plot_overview is not None
    assert state.get("global_summary")  # set from plot_overview.plot_summary


def test_run_analysis_deterministic_chunk_ids():
    doc = RawDocument(text="A.\n\nB.\n\nC.")
    genre = GenreIntention(genre="thriller")
    state1, _ = run_analysis(doc, genre, "run-a")
    state2, _ = run_analysis(doc, genre, "run-b")
    ids1 = [c.id for c in state1["chunks"]]
    ids2 = [c.id for c in state2["chunks"]]
    assert ids1 == ids2 == ["c1", "c2", "c3"]
