"""Inkblot persona, explicit context, and story chat."""

from __future__ import annotations

from narrative_dag.contracts import StoryChatRequest
from narrative_dag.db import init_db
from narrative_dag.explicit_context import build_explicit_context
from narrative_dag.persona.refresh_job import run_persona_refresh_job
from narrative_dag.store.document_store import DocumentStore
from narrative_dag.store.job_store import JobStore
from narrative_dag.store.persona_store import PersonaStore
from narrative_dag.store.story_chat_store import StoryChatStore
from narrative_dag.inkblot_memory_jobs import (
    count_inkblot_user_turns,
    run_inkblot_memory_batch_job,
)
from narrative_dag.service import NarrativeAnalysisService
from narrative_dag.story_chat import build_inkblot_judgment_context, writer_memory_subset_for_prompt
from narrative_dag.store.run_store import RunStore
from narrative_dag.schemas import Chunk
from narrative_dag.store.inkblot_memory_store import InkblotMemoryStore


def test_explicit_context_manuscript_prefix(temp_db_path):
    conn = init_db(temp_db_path)
    try:
        ds = DocumentStore(conn)
        doc_id = ds.create_document(title="T", author="A")
        rid = ds.create_revision(doc_id, "One two three. " * 200)
        man, text, err = build_explicit_context(ds, revision_id=rid, chunk_ids=None, chapter_id=None)
        assert err is None
        assert man.get("scope") == "manuscript_prefix"
        assert len(text.split()) <= 5000
    finally:
        conn.close()


def test_explicit_context_chunk_ids_ordered(temp_db_path):
    conn = init_db(temp_db_path)
    try:
        ds = DocumentStore(conn)
        doc_id = ds.create_document()
        text = "AAA\n\nBBB\n\nCCC"
        rid = ds.create_revision(doc_id, text)
        from narrative_dag.schemas import Chunk

        chunks = [
            Chunk(id="c1", text="AAA", position=0, start_char=0, end_char=3),
            Chunk(id="c2", text="BBB", position=1, start_char=5, end_char=8),
            Chunk(id="c3", text="CCC", position=2, start_char=10, end_char=13),
        ]
        ds.replace_chunk_versions(rid, chunks)
        man, out, err = build_explicit_context(ds, revision_id=rid, chunk_ids=["c2", "c1"], chapter_id=None)
        assert err is None
        assert "BBB" in out and "AAA" in out
        # Hydration sorts by chunk position, not request order
        assert out.index("AAA") < out.index("BBB")
    finally:
        conn.close()


def test_persona_refresh_job_writes_snapshot(temp_db_path, monkeypatch):
    monkeypatch.delenv("EDITR_DISABLE_PERSONA_REFRESH", raising=False)
    # Avoid daemon thread from analyze() racing with teardown on Windows (SQLite file lock).
    monkeypatch.setattr(
        "narrative_dag.service.schedule_persona_refresh_after_analyze",
        lambda *args, **kwargs: None,
    )
    svc = NarrativeAnalysisService(db_path=temp_db_path)
    try:
        req = __import__("narrative_dag.contracts", fromlist=["AnalyzeDocumentRequest"]).AnalyzeDocumentRequest(
            document_text="First.\n\nSecond.\n\nThird.\n\nFourth.",
            genre="literary_fiction",
        )
        resp = svc.analyze_document(req)
        assert resp.success
        assert resp.document_id
        assert resp.revision_id
        conn = init_db(temp_db_path)
        try:
            js = JobStore(conn)
            jid = js.create_job(
                "persona_refresh",
                document_id=resp.document_id,
                revision_id=resp.revision_id,
                run_id=resp.run_id,
                payload={
                    "document_id": resp.document_id,
                    "revision_id": resp.revision_id,
                    "run_id": resp.run_id,
                },
            )
            run_persona_refresh_job(temp_db_path, jid)
            job = js.get_job(jid)
            assert job and job["status"] == "succeeded"
            ps = PersonaStore(conn)
            snap = ps.get_latest_snapshot(resp.document_id)
            assert snap is not None
            assert snap["version"] >= 1
        finally:
            conn.close()
    finally:
        svc.close()


def test_story_chat_requires_document(temp_db_path):
    svc = NarrativeAnalysisService(db_path=temp_db_path)
    try:
        conn = init_db(temp_db_path)
        try:
            ds = DocumentStore(conn)
            document_id = ds.create_document()
            revision_id = ds.create_revision(document_id, "hello world " * 50)
        finally:
            conn.close()
        out = svc.story_chat(
            document_id,
            StoryChatRequest(user_message="What is the tone?", revision_id=revision_id, max_words=100),
        )
        assert out.success
        assert out.session_id
        assert out.answer
    finally:
        svc.close()


def test_story_chat_session_roundtrip(temp_db_path):
    conn = init_db(temp_db_path)
    try:
        sc = StoryChatStore(conn)
        ds = DocumentStore(conn)
        doc = ds.create_document()
        sid = sc.create_session(doc, revision_id="rev-x")
        sc.append_turn(sid, role="user", content="hi", context_manifest={"k": 1})
        turns = sc.list_turns(sid)
        assert len(turns) == 1
        assert turns[0]["role"] == "user"
    finally:
        conn.close()


def test_count_inkblot_user_turns_excludes_quick_coach():
    turns = [
        {"role": "user", "context_manifest": {"source": "quick_coach"}},
        {"role": "assistant", "context_manifest": {}},
        {"role": "user", "context_manifest": {}},
        {"role": "assistant", "context_manifest": {}},
    ]
    assert count_inkblot_user_turns(turns) == 1


def test_writer_memory_subset_for_prompt_filters_keys():
    out = writer_memory_subset_for_prompt(
        {"rolling_summary": "x", "open_goals": ["g"], "noise": 1, "noted_emotions": []}
    )
    assert out is not None
    assert "noise" not in out
    assert "noted_emotions" not in out


def test_inkblot_memory_batch_job_writes_payload(temp_db_path, monkeypatch):
    monkeypatch.setenv("EDITR_DISABLE_INKBLOT_MEMORY_JOBS", "0")
    conn = init_db(temp_db_path)
    try:
        ds = DocumentStore(conn)
        sc = StoryChatStore(conn)
        js = JobStore(conn)
        doc_id = ds.create_document()
        sid = sc.create_session(doc_id, revision_id="r1")
        for i in range(5):
            sc.append_turn(sid, role="user", content=f"u{i}", context_manifest={})
            sc.append_turn(sid, role="assistant", content=f"a{i}", context_manifest={})
        jid = js.create_job(
            "inkblot_memory_batch",
            document_id=doc_id,
            payload={
                "document_id": doc_id,
                "session_id": sid,
                "dedupe_key": "test",
                "provider": None,
            },
        )
        run_inkblot_memory_batch_job(temp_db_path, jid)
        job = js.get_job(jid)
        assert job and job["status"] == "succeeded"
        mem = InkblotMemoryStore(conn).get_payload(doc_id)
        assert mem.get("rolling_summary")
    finally:
        conn.close()


def test_story_chat_session_close_schedules_job(temp_db_path):
    svc = NarrativeAnalysisService(db_path=temp_db_path)
    try:
        conn = init_db(temp_db_path)
        try:
            ds = DocumentStore(conn)
            doc_id = ds.create_document()
            sc = StoryChatStore(conn)
            sid = sc.create_session(doc_id, revision_id="r1")
        finally:
            conn.close()
        out = svc.story_chat_session_close(doc_id, sid, None)
        assert out.success and out.scheduled
        conn = init_db(temp_db_path)
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT status FROM async_jobs WHERE kind = 'inkblot_memory_close' AND document_id = ?",
                (doc_id,),
            )
            row = cur.fetchone()
            assert row is not None
        finally:
            conn.close()
    finally:
        svc.close()


def test_build_inkblot_judgment_context_reads_artifacts(temp_db_path):
    conn = init_db(temp_db_path)
    try:
        ds = DocumentStore(conn)
        rs = RunStore(conn)
        doc_id = ds.create_document()
        rid = ds.create_revision(doc_id, "Text one.\n\nText two.")
        ck = Chunk(id="c1", text="Text one.", position=0, start_char=0, end_char=9)
        ds.replace_chunk_versions(rid, [ck])
        run_id = "run-judge-ctx"
        rs.save_run_meta(run_id, document_id=doc_id, revision_id=rid, analysis_kind="full")
        payload = {
            "target_chunk": ck.model_dump(),
            "current_judgment": {
                "decision": "rewrite",
                "severity": 0.7,
                "reasoning": "Needs polish.",
                "core_issue": "pacing",
                "guidance": "tighten",
            },
            "critic_result": {"critique": "too slow", "verdict": "weak", "failure_points": ["x"]},
            "defense_result": {"defense": "intentional", "salvageability": "medium", "valid_points": ["y"]},
        }
        rs.save_chunk_artifact(run_id, "c1", 0, payload)
        text, found = build_inkblot_judgment_context(rs, run_id, ["c1"])
        assert found["c1"] is True
        assert text
        assert "Editor judgment" in text and "Critic" in text and "Advocate" in text
    finally:
        conn.close()


def test_story_chat_chunk_ids_adds_judgment_manifest(temp_db_path, monkeypatch):
    monkeypatch.setattr("narrative_dag.service.run_inkblot_chat", lambda **kwargs: "stub-reply")
    conn = init_db(temp_db_path)
    try:
        ds = DocumentStore(conn)
        rs = RunStore(conn)
        doc_id = ds.create_document()
        rid = ds.create_revision(doc_id, "Text one.\n\nText two.")
        ck = Chunk(id="c1", text="Text one.", position=0, start_char=0, end_char=9)
        ds.replace_chunk_versions(rid, [ck])
        run_id = "run-judge-ctx-2"
        rs.save_run_meta(run_id, document_id=doc_id, revision_id=rid, analysis_kind="full")
        payload = {
            "target_chunk": ck.model_dump(),
            "current_judgment": {
                "decision": "keep",
                "severity": 0.2,
                "reasoning": "ok",
                "core_issue": "",
                "guidance": "",
            },
            "critic_result": {"critique": "c", "verdict": "borderline", "failure_points": []},
            "defense_result": {"defense": "d", "salvageability": "high", "valid_points": []},
        }
        rs.save_chunk_artifact(run_id, "c1", 0, payload)
    finally:
        conn.close()

    svc = NarrativeAnalysisService(db_path=temp_db_path)
    try:
        out = svc.story_chat(
            doc_id,
            StoryChatRequest(
                user_message="Hello inkblot",
                revision_id=rid,
                max_words=500,
                chunk_ids=["c1"],
            ),
        )
        assert out.success
        assert out.context_manifest.get("judgment_run_id") == run_id
        assert out.context_manifest.get("chunk_judgment_artifact_present", {}).get("c1") is True
    finally:
        svc.close()


def test_get_story_persona_empty(temp_db_path):
    svc = NarrativeAnalysisService(db_path=temp_db_path)
    try:
        conn = init_db(temp_db_path)
        try:
            ds = DocumentStore(conn)
            doc_id = ds.create_document()
        finally:
            conn.close()
        pr = svc.get_story_persona(doc_id)
        assert pr.document_id == doc_id
        assert pr.snapshot is None
    finally:
        svc.close()
