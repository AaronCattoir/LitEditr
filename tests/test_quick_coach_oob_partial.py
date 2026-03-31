"""Quick coach OOB threshold and partial analyze merge."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from narrative_dag.api import app as app_module
from narrative_dag.contracts import AnalyzeDocumentRequest, ClientChunkSpan
from narrative_dag.db import init_db
from narrative_dag.service import NarrativeAnalysisService
from narrative_dag.store.document_store import DocumentStore
from narrative_dag.store.run_store import RunStore


def _reset_app_singletons() -> None:
    app_module._service = None
    app_module._job_store = None


@pytest.fixture
def client_isolated(monkeypatch, tmp_path):
    db_path = str(tmp_path / "oob.sqlite")
    monkeypatch.setattr("narrative_dag.config.DEFAULT_DB_PATH", db_path)
    _reset_app_singletons()
    init_db(db_path)
    from narrative_dag.api.app import app

    return TestClient(app)


def test_quick_coach_oob_422(client_isolated, monkeypatch, tmp_path):
    db_path = str(tmp_path / "seed_oob.sqlite")
    monkeypatch.setattr("narrative_dag.config.DEFAULT_DB_PATH", db_path)
    _reset_app_singletons()
    init_db(db_path)
    from narrative_dag.api.app import app

    client = TestClient(app)
    conn = init_db(db_path)
    rs = RunStore(conn)
    ds = DocumentStore(conn)
    doc_id = ds.create_document(title="T")
    rev_row = ds.create_revision(doc_id, "Hello world.")
    rs.save_run_meta("run-oob", genre="literary_fiction", document_id=doc_id, revision_id=rev_row)
    from narrative_dag.schemas import CharacterDatabase, CharacterEntry, Chunk, DocumentState, PlotOverview

    ds_state = DocumentState(
        plot_overview=PlotOverview(story_point="x", plot_summary="y"),
        character_database=CharacterDatabase(characters=[CharacterEntry(canonical_name="A")]),
    )
    rs.save_document_state("run-oob", ds_state)
    ch = Chunk(id="c1", text="short", position=0, start_char=0, end_char=5)
    rs.save_chunk_artifact(
        "run-oob",
        "c1",
        0,
        {
            "target_chunk": ch.model_dump(),
            "context_window": {
                "target_chunk": ch.model_dump(),
                "previous_chunks": [],
                "next_chunks": [],
                "global_summary": "",
            },
            "detector_results": {},
            "critic_result": None,
            "defense_result": None,
            "current_judgment": None,
        },
    )

    monkeypatch.setattr("narrative_dag.config.QUICK_COACH_OOB_MIN_CHARS", 2)
    monkeypatch.setattr("narrative_dag.config.QUICK_COACH_OOB_MAX_CHARS", 100)
    monkeypatch.setattr("narrative_dag.config.QUICK_COACH_OOB_RATIO", 0.3)

    r = client.post(
        f"/v1/revisions/{rev_row}/quick-coach",
        json={"chunk_id": "c1", "current_chunk_text": "x" * 50},
    )
    assert r.status_code == 422
    body = r.json()["detail"]
    assert body["error_code"] == "quick_coach_oob"
    assert body["requires_reanalysis"] is True


def test_partial_analyze_merges_chunk_artifacts(temp_db_path):
    doc_text = "First.\n\nSecond."
    spans = [
        ClientChunkSpan(chunk_id="c1", start_char=0, end_char=8),
        ClientChunkSpan(chunk_id="c2", start_char=8, end_char=15),
    ]
    svc = NarrativeAnalysisService(db_path=temp_db_path)
    conn = init_db(temp_db_path)
    ds = DocumentStore(conn)
    doc_id = ds.create_document(title="P")

    full = AnalyzeDocumentRequest(
        document_text=doc_text,
        genre="literary_fiction",
        document_id=doc_id,
        chunks=list(spans),
    )
    r1 = svc.analyze_document(full)
    assert r1.success
    assert r1.analysis_kind == "full"
    assert len(r1.report.chunk_judgments) == 2

    doc_text2 = "First.\n\nSecond!!"
    spans2 = [
        ClientChunkSpan(chunk_id="c1", start_char=0, end_char=8),
        ClientChunkSpan(chunk_id="c2", start_char=8, end_char=16),
    ]
    partial = AnalyzeDocumentRequest(
        document_text=doc_text2,
        genre="literary_fiction",
        document_id=doc_id,
        revision_id=r1.revision_id,
        chunks=list(spans2),
        base_run_id=r1.run_id,
        only_chunk_ids=["c2"],
    )
    r2 = svc.analyze_document(partial)
    assert r2.success
    assert r2.analysis_kind == "partial"
    assert len(r2.report.chunk_judgments) == 2
    rs = RunStore(conn)
    rows = rs.list_chunks_for_run(r2.run_id)
    assert len(rows) == 2
    a1 = rs.get_chunk_artifact(r2.run_id, "c1")
    a2 = rs.get_chunk_artifact(r2.run_id, "c2")
    assert a1 and a2
    assert a1["target_chunk"]["text"] == "First.\n\n"
    assert "!!" in a2["target_chunk"]["text"]
    svc.close()
    conn.close()


def test_analyze_partial_requires_pair():
    with pytest.raises(ValueError, match="base_run_id"):
        AnalyzeDocumentRequest(
            document_text="a",
            genre="literary_fiction",
            only_chunk_ids=["c1"],
            chunks=[ClientChunkSpan(chunk_id="c1", start_char=0, end_char=1)],
        )


def test_partial_analyze_new_middle_chunk_id_merges_from_base(temp_db_path):
    """Inserted section id is not in base run; partial analyzes it and copies neighbors from base."""
    doc_full = "First.\n\nSecond."
    spans_full = [
        ClientChunkSpan(chunk_id="c1", start_char=0, end_char=8),
        ClientChunkSpan(chunk_id="c2", start_char=8, end_char=15),
    ]
    doc_insert = "First.\n\nMiddle.\n\nSecond."
    spans_insert = [
        ClientChunkSpan(chunk_id="c1", start_char=0, end_char=8),
        ClientChunkSpan(chunk_id="c_mid", start_char=8, end_char=16),
        ClientChunkSpan(chunk_id="c2", start_char=16, end_char=24),
    ]
    svc = NarrativeAnalysisService(db_path=temp_db_path)
    conn = init_db(temp_db_path)
    ds = DocumentStore(conn)
    doc_id = ds.create_document(title="Mid")

    full = AnalyzeDocumentRequest(
        document_text=doc_full,
        genre="literary_fiction",
        document_id=doc_id,
        chunks=list(spans_full),
    )
    r1 = svc.analyze_document(full)
    assert r1.success
    rs = RunStore(conn)
    assert rs.has_chunk_artifact(r1.run_id, "c1")
    assert rs.has_chunk_artifact(r1.run_id, "c2")
    assert not rs.has_chunk_artifact(r1.run_id, "c_mid")

    partial = AnalyzeDocumentRequest(
        document_text=doc_insert,
        genre="literary_fiction",
        document_id=doc_id,
        revision_id=r1.revision_id,
        chunks=list(spans_insert),
        base_run_id=r1.run_id,
        only_chunk_ids=["c_mid"],
    )
    r2 = svc.analyze_document(partial)
    assert r2.success
    assert r2.analysis_kind == "partial"
    rows = rs.list_chunks_for_run(r2.run_id)
    assert len(rows) == 3
    a_mid = rs.get_chunk_artifact(r2.run_id, "c_mid")
    a1 = rs.get_chunk_artifact(r2.run_id, "c1")
    assert a_mid and a1
    assert "Middle" in (a_mid.get("target_chunk") or {}).get("text", "")
    svc.close()
    conn.close()
