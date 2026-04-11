"""Dialectic depth routing, prompts, and context bundle."""

from __future__ import annotations

import narrative_dag.graph as graph_mod
from narrative_dag.db import init_db
from narrative_dag.graph import run_analysis
from narrative_dag.prompt_context import build_prompt_context
from narrative_dag.prompts.judgment import editor_judgment_prompt
from narrative_dag.schemas import (
    Chunk,
    ContextWindow,
    DocumentState,
    GenreIntention,
    RawDocument,
)
from narrative_dag.store.document_store import DocumentStore
from narrative_dag.store.run_store import RunStore


def _wrap_count(orig, counts: dict[str, int], key: str):
    def _w(state):
        counts[key] = counts.get(key, 0) + 1
        return orig(state)

    return _w


def _one_chunk():
    text = "Single paragraph only."
    return RawDocument(text=text), [
        Chunk(id="c1", text=text, position=0, start_char=0, end_char=len(text)),
    ]


def test_dialectic_depth_off_skips_mediator(monkeypatch):
    doc, client_chunks = _one_chunk()
    genre = GenreIntention(genre="literary_fiction")
    counts: dict[str, int] = {}

    monkeypatch.setattr(
        graph_mod,
        "evidence_synthesizer",
        _wrap_count(graph_mod.evidence_synthesizer, counts, "es"),
    )
    monkeypatch.setattr(
        graph_mod,
        "dialectic_mediator",
        _wrap_count(graph_mod.dialectic_mediator, counts, "med"),
    )
    monkeypatch.setattr(
        graph_mod,
        "dialectic_synthesizer",
        _wrap_count(graph_mod.dialectic_synthesizer, counts, "syn"),
    )
    monkeypatch.setattr(
        graph_mod,
        "editor_judge",
        _wrap_count(graph_mod.editor_judge, counts, "judge"),
    )

    run_analysis(doc, genre, "run-d-off", client_chunks=client_chunks, dialectic_depth="off")
    assert counts.get("es") == 1 and counts.get("judge") == 1
    assert counts.get("med", 0) == 0 and counts.get("syn", 0) == 0


def test_dialectic_depth_review_runs_mediation_only(monkeypatch):
    doc, client_chunks = _one_chunk()
    genre = GenreIntention(genre="literary_fiction")
    counts: dict[str, int] = {}

    monkeypatch.setattr(
        graph_mod,
        "evidence_synthesizer",
        _wrap_count(graph_mod.evidence_synthesizer, counts, "es"),
    )
    monkeypatch.setattr(
        graph_mod,
        "dialectic_mediator",
        _wrap_count(graph_mod.dialectic_mediator, counts, "med"),
    )
    monkeypatch.setattr(
        graph_mod,
        "dialectic_synthesizer",
        _wrap_count(graph_mod.dialectic_synthesizer, counts, "syn"),
    )
    monkeypatch.setattr(
        graph_mod,
        "editor_judge",
        _wrap_count(graph_mod.editor_judge, counts, "judge"),
    )

    run_analysis(doc, genre, "run-d-review", client_chunks=client_chunks, dialectic_depth="review")
    assert counts.get("es") == 1 and counts.get("med") == 1 and counts.get("judge") == 1
    assert counts.get("syn", 0) == 0


def test_dialectic_depth_deep_runs_synthesis(monkeypatch):
    doc, client_chunks = _one_chunk()
    genre = GenreIntention(genre="literary_fiction")
    counts: dict[str, int] = {}

    monkeypatch.setattr(
        graph_mod,
        "evidence_synthesizer",
        _wrap_count(graph_mod.evidence_synthesizer, counts, "es"),
    )
    monkeypatch.setattr(
        graph_mod,
        "dialectic_mediator",
        _wrap_count(graph_mod.dialectic_mediator, counts, "med"),
    )
    monkeypatch.setattr(
        graph_mod,
        "dialectic_synthesizer",
        _wrap_count(graph_mod.dialectic_synthesizer, counts, "syn"),
    )
    monkeypatch.setattr(
        graph_mod,
        "editor_judge",
        _wrap_count(graph_mod.editor_judge, counts, "judge"),
    )

    run_analysis(doc, genre, "run-d-deep", client_chunks=client_chunks, dialectic_depth="deep")
    assert counts == {"es": 1, "med": 1, "syn": 1, "judge": 1}


def test_editor_judgment_prompt_includes_dialectic_sections():
    prompt_ctx = build_prompt_context(
        {
            "context_window": ContextWindow(
                target_chunk=Chunk(id="c1", text="Hi.", position=0, start_char=0, end_char=3),
                previous_chunks=[],
                next_chunks=[],
                global_summary="",
            ),
            "genre_intention": GenreIntention(genre="literary_fiction"),
            "document_state": DocumentState(),
        }
    )
    p = editor_judgment_prompt(
        prompt_ctx,
        "drift: {}",
        '{"critique":"x"}',
        '{"defense":"y"}',
        dialectic_mediation='{"strongest_points":"a"}',
        dialectic_synthesis='{"integrated_perspective":"b"}',
    )
    assert "Dialectic mediation" in p and "strongest_points" in p
    assert "Dialectic synthesis" in p and "integrated_perspective" in p


def test_get_context_bundle_dialectic_optional(temp_db_path):
    conn = init_db(temp_db_path)
    try:
        ds = DocumentStore(conn)
        rs = RunStore(conn)
        doc_id = ds.create_document()
        rid = ds.create_revision(doc_id, "Hello.")
        ck = Chunk(id="c1", text="Hello.", position=0, start_char=0, end_char=6)
        ds.replace_chunk_versions(rid, [ck])
        run_id = "run-dial-bundle"
        rs.save_run_meta(run_id, document_id=doc_id, revision_id=rid, analysis_kind="full")
        minimal = {
            "target_chunk": ck.model_dump(),
            "current_judgment": {
                "decision": "keep",
                "severity": 0.0,
                "reasoning": "",
                "core_issue": "",
                "guidance": "",
            },
            "critic_result": {"critique": "", "verdict": "borderline", "failure_points": []},
            "defense_result": {"defense": "", "salvageability": "medium", "valid_points": []},
        }
        rs.save_chunk_artifact(run_id, "c1", 0, minimal)
        b = rs.get_context_bundle(run_id, "c1")
        assert b is not None
        assert b.dialectic_mediation is None and b.dialectic_synthesis is None

        with_d = {
            **minimal,
            "dialectic_mediation": {
                "strongest_points": "sp",
                "contradictions": "",
                "assumptions_and_values": "",
                "limitations": "",
                "core_tension_summary": "",
            },
        }
        rs.save_chunk_artifact(run_id, "c1", 0, with_d)
        b2 = rs.get_context_bundle(run_id, "c1")
        assert b2 is not None and b2.dialectic_mediation is not None
        assert b2.dialectic_mediation.strongest_points == "sp"
    finally:
        conn.close()
