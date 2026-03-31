"""FastAPI application: documents, revisions, async jobs, chat, SSE progress stream."""

from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

import narrative_dag.config as config_module
from narrative_dag.chunk_spans import validate_and_build_chunks_from_spans
from narrative_dag.contracts import AnalyzeDocumentRequest, ChatRequest, QuickCoachRequest
from narrative_dag.db import init_db
from narrative_dag.llm import runtime_providers_public_view
from narrative_dag.service import NarrativeAnalysisService
from narrative_dag.store.document_store import DocumentStore
from narrative_dag.store.job_store import JobStore
from narrative_dag.store.run_store import RunStore, document_state_has_story_map, serialize_story_wide_for_api

_service: NarrativeAnalysisService | None = None
_job_store: JobStore | None = None


def get_service() -> NarrativeAnalysisService:
    global _service
    if _service is None:
        _service = NarrativeAnalysisService()
    return _service


def get_job_store() -> JobStore:
    global _job_store
    if _job_store is None:
        conn = init_db(config_module.DEFAULT_DB_PATH)
        _job_store = JobStore(conn)
    return _job_store


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    get_service()
    get_job_store()
    yield


app = FastAPI(title="editr API", version="0.2.0", lifespan=_lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/v1/runtime/providers")
def get_runtime_providers() -> dict[str, Any]:
    """Beta LLM backends (openai/gemini): configuration flags and default model ids (no secrets)."""
    return runtime_providers_public_view()


@app.get("/v1/documents")
def list_documents(limit: int = 100, offset: int = 0) -> dict[str, Any]:
    conn = init_db(config_module.DEFAULT_DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT document_id, title, author, created_at
        FROM documents
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
        """,
        (limit, offset),
    )
    rows = cur.fetchall()
    return {
        "documents": [
            {"document_id": r[0], "title": r[1], "author": r[2], "created_at": r[3]}
            for r in rows
        ]
    }


@app.post("/v1/documents")
def create_document(
    title: str | None = None,
    author: str | None = None,
) -> dict[str, Any]:
    conn = init_db(config_module.DEFAULT_DB_PATH)
    ds = DocumentStore(conn)
    doc_id = ds.create_document(title=title, author=author)
    return {"document_id": doc_id}


@app.get("/v1/documents/{document_id}/chapters")
def list_document_chapters(document_id: str) -> dict[str, Any]:
    conn = init_db(config_module.DEFAULT_DB_PATH)
    ds = DocumentStore(conn)
    if not ds.document_exists(document_id):
        raise HTTPException(404, "document not found")
    return {
        "document_id": document_id,
        "chapters": ds.list_document_chapters(document_id),
    }


@app.post("/v1/documents/{document_id}/chapters")
def create_document_chapter(document_id: str, body: dict[str, Any]) -> dict[str, Any]:
    conn = init_db(config_module.DEFAULT_DB_PATH)
    ds = DocumentStore(conn)
    if not ds.document_exists(document_id):
        raise HTTPException(404, "document not found")
    title = body.get("title", "")
    if not isinstance(title, str):
        raise HTTPException(400, "title must be a string")
    sort_order = body.get("sort_order")
    if sort_order is not None and not isinstance(sort_order, int):
        raise HTTPException(400, "sort_order must be an integer")
    chapter_id = ds.create_document_chapter(document_id, title, sort_order=sort_order)
    return {"chapter_id": chapter_id, "document_id": document_id}


@app.patch("/v1/chapters/{chapter_id}")
def update_document_chapter(chapter_id: str, body: dict[str, Any]) -> dict[str, Any]:
    conn = init_db(config_module.DEFAULT_DB_PATH)
    ds = DocumentStore(conn)
    if not ds.get_document_id_for_chapter(chapter_id):
        raise HTTPException(404, "chapter not found")
    title = body.get("title")
    sort_order = body.get("sort_order")
    if title is not None and not isinstance(title, str):
        raise HTTPException(400, "title must be a string")
    if sort_order is not None and not isinstance(sort_order, int):
        raise HTTPException(400, "sort_order must be an integer")
    if title is None and sort_order is None:
        raise HTTPException(400, "provide title and/or sort_order")
    updated = ds.update_document_chapter(chapter_id, title=title, sort_order=sort_order)
    return {"updated": updated, "chapter_id": chapter_id}


@app.delete("/v1/chapters/{chapter_id}")
def delete_document_chapter(chapter_id: str) -> dict[str, Any]:
    conn = init_db(config_module.DEFAULT_DB_PATH)
    ds = DocumentStore(conn)
    if not ds.delete_document_chapter(chapter_id):
        raise HTTPException(404, "chapter not found")
    return {"deleted": True, "chapter_id": chapter_id}


@app.get("/v1/documents/{document_id}/manuscript")
def get_document_manuscript(document_id: str) -> dict[str, Any]:
    conn = init_db(config_module.DEFAULT_DB_PATH)
    ds = DocumentStore(conn)
    if not ds.document_exists(document_id):
        raise HTTPException(404, "document not found")
    rev = ds.get_current_revision_for_document(document_id)
    return {
        "document_id": document_id,
        "chapters": ds.list_document_chapters(document_id),
        "current_revision": rev,
    }


@app.post("/v1/documents/{document_id}/revisions")
def submit_revision(document_id: str, body: dict[str, Any]) -> dict[str, Any]:
    text = body.get("text") or body.get("document_text")
    if not text or not isinstance(text, str):
        raise HTTPException(400, "text or document_text required")
    conn = init_db(config_module.DEFAULT_DB_PATH)
    ds = DocumentStore(conn)
    parent = body.get("parent_revision_id")
    rid = ds.create_revision(document_id, text, parent_revision_id=parent)
    ds.record_revision_event(document_id, rid, "submit", from_revision_id=parent)
    return {"revision_id": rid, "document_id": document_id}


def build_analyze_payload_from_revision(
    rev: dict[str, Any], revision_id: str, body: dict[str, Any]
) -> dict[str, Any]:
    """Shared payload for async analyze (Submit All and sparkle auto-queue)."""
    return {
        "document_text": rev.get("full_text") or "",
        "genre": body.get("genre") or "literary_fiction",
        "subgenre_tags": body.get("subgenre_tags") or [],
        "tone_descriptors": body.get("tone_descriptors") or [],
        "reference_authors": body.get("reference_authors") or [],
        "title": body.get("title"),
        "author": body.get("author"),
        "document_id": rev["document_id"],
        "revision_id": revision_id,
        "chunks": body.get("chunks"),
        "base_run_id": body.get("base_run_id"),
        "only_chunk_ids": body.get("only_chunk_ids"),
        "short_story_single_chapter": bool(body.get("short_story_single_chapter", False)),
        "provider": body.get("provider"),
    }


def _validate_optional_client_chunks(document_text: str, body: dict[str, Any]) -> None:
    raw = body.get("chunks")
    if not raw:
        return
    if not isinstance(raw, list) or len(raw) == 0:
        return
    try:
        spans = []
        for item in raw:
            if not isinstance(item, dict):
                raise ValueError("each chunk must be an object")
            spans.append(
                (str(item["chunk_id"]), int(item["start_char"]), int(item["end_char"]))
            )
        validate_and_build_chunks_from_spans(document_text, spans)
    except (KeyError, TypeError, ValueError) as e:
        raise HTTPException(422, str(e)) from e


def enqueue_analyze_revision(
    revision_id: str,
    body: dict[str, Any],
    background_tasks: BackgroundTasks,
    *,
    lenient_client_chunks: bool = False,
) -> tuple[str, str]:
    """Create analyze job or return existing active job. Returns (job_id, reason).

    When ``lenient_client_chunks`` is False (default), invalid optional ``chunks`` in ``body``
    raise HTTPException 422 so direct ``POST .../analyze`` callers get a clear validation error.

    When True (quick-coach enqueue), bad client spans are cleared so analysis can still queue:
    editor text can disagree with persisted revision text (line endings, unsaved edits).
    """
    conn = init_db(config_module.DEFAULT_DB_PATH)
    ds = DocumentStore(conn)
    rev = ds.get_revision(revision_id)
    if not rev:
        raise HTTPException(404, "revision not found")
    try:
        _validate_optional_client_chunks(rev.get("full_text") or "", body)
    except HTTPException:
        if not lenient_client_chunks:
            raise
        body["chunks"] = None

    job_store = get_job_store()
    existing = job_store.find_active_analyze_job_for_revision(revision_id)
    if existing:
        return existing, "full_analysis_already_queued"
    payload = build_analyze_payload_from_revision(rev, revision_id, body)
    job_id = job_store.create_job(
        "analyze",
        document_id=rev["document_id"],
        revision_id=revision_id,
        payload=payload,
    )
    background_tasks.add_task(_run_analyze_job, job_id, payload)
    return job_id, "full_analysis_required"


def _find_latest_ancestor_run_with_story_map(
    conn: Any, rs: RunStore, revision_id: str, max_hops: int = 50
) -> str | None:
    """Walk revision ancestry and return newest run with story map context."""
    cur = conn.cursor()
    current = revision_id
    hops = 0
    while current and hops < max_hops:
        cur.execute(
            "SELECT parent_revision_id FROM document_revisions WHERE revision_id = ?",
            (current,),
        )
        row = cur.fetchone()
        parent = str(row[0]) if row and row[0] else None
        if not parent:
            return None
        run_id = rs.find_latest_run_with_story_map(parent)
        if run_id:
            return run_id
        current = parent
        hops += 1
    return None


def _run_analyze_job(job_id: str, payload: dict[str, Any]) -> None:
    js = get_job_store()
    svc = get_service()
    try:
        js.update_job(job_id, "running")
        req = AnalyzeDocumentRequest.model_validate(payload)
        resp = svc.analyze_document(req)
        if not resp.success:
            js.update_job(job_id, "failed", error=resp.error or "analyze failed")
            return
        js.update_job(
            job_id,
            "succeeded",
            result={
                "run_id": resp.run_id,
                "document_id": resp.document_id,
                "revision_id": resp.revision_id,
                "report": resp.report.model_dump(),
                "analysis_kind": resp.analysis_kind,
            },
            run_id=resp.run_id,
        )
    except Exception as e:
        js.update_job(job_id, "failed", error=str(e))


@app.post("/v1/revisions/{revision_id}/analyze")
async def analyze_revision(
    revision_id: str,
    background_tasks: BackgroundTasks,
    body: dict[str, Any],
) -> JSONResponse:
    job_id, reason = enqueue_analyze_revision(revision_id, body, background_tasks)
    return JSONResponse(
        {"job_id": job_id, "status": "queued", "reason": reason},
        status_code=202,
    )


@app.post("/v1/revisions/{revision_id}/quick-coach")
async def quick_coach_revision(
    revision_id: str,
    background_tasks: BackgroundTasks,
    body: dict[str, Any],
) -> JSONResponse:
    req = QuickCoachRequest.model_validate(body)
    conn = init_db(config_module.DEFAULT_DB_PATH)
    ds = DocumentStore(conn)
    rs = RunStore(conn)
    rev = ds.get_revision(revision_id)
    if not rev:
        raise HTTPException(404, "revision not found")

    analyze_body = {
        "genre": req.genre,
        "subgenre_tags": req.subgenre_tags,
        "tone_descriptors": req.tone_descriptors,
        "reference_authors": req.reference_authors,
        "title": req.title,
        "author": req.author,
        "chunks": [c.model_dump() for c in req.chunks] if req.chunks else None,
        "short_story_single_chapter": req.short_story_single_chapter,
        "provider": req.provider,
    }

    effective_run_id: str | None = req.run_id
    if effective_run_id:
        rid_for_run = rs.get_revision_id_for_run(effective_run_id)
        if rid_for_run != revision_id:
            raise HTTPException(422, "run_id does not belong to this revision")
        ds_run = rs.get_document_state(effective_run_id)
        if not ds_run or not document_state_has_story_map(ds_run):
            raise HTTPException(422, "run has no story map for quick coach")
        if not rs.get_chunk_artifact(effective_run_id, req.chunk_id):
            raise HTTPException(422, "chunk not found in this run")
    else:
        effective_run_id = rs.find_latest_run_with_story_map(revision_id)
        if not effective_run_id:
            effective_run_id = _find_latest_ancestor_run_with_story_map(conn, rs, revision_id)
            
        if not effective_run_id or not rs.has_chunk_artifact(effective_run_id, req.chunk_id):
            base_run_id = effective_run_id or _find_latest_ancestor_run_with_story_map(conn, rs, revision_id)
            if base_run_id and req.chunks:
                partial_body = {
                    **analyze_body,
                    "base_run_id": base_run_id,
                    "only_chunk_ids": [req.chunk_id],
                }
                try:
                    job_id, _ = enqueue_analyze_revision(
                        revision_id,
                        partial_body,
                        background_tasks,
                        lenient_client_chunks=True,
                    )
                    return JSONResponse(
                        {
                            "job_id": job_id,
                            "status": "queued",
                            "reason": "partial_analysis_required",
                        },
                        status_code=202,
                    )
                except HTTPException as e:
                    if e.status_code != 422:
                        raise
                    pass
                    
            job_id, reason = enqueue_analyze_revision(
                revision_id,
                analyze_body,
                background_tasks,
                lenient_client_chunks=True,
            )
            return JSONResponse(
                {
                    "job_id": job_id,
                    "status": "queued",
                    "reason": reason,
                },
                status_code=202,
            )

    assert effective_run_id is not None
    svc = get_service()
    resp = svc.quick_coach_advice(
        effective_run_id,
        req.chunk_id,
        revision_id,
        req.focus,
        current_chunk_text=req.current_chunk_text,
        short_story_single_chapter=req.short_story_single_chapter,
        provider=req.provider,
    )
    if not resp.success:
        code = resp.error_code or ""
        if code == "quick_coach_oob":
            raise HTTPException(status_code=422, detail=resp.model_dump(exclude_none=True))
        status = 404 if code == "chunk_not_in_run" else 500
        raise HTTPException(status, resp.error or "quick coach failed")
    return JSONResponse(resp.model_dump(), status_code=200)


@app.get("/v1/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    j = get_job_store().get_job(job_id)
    if not j:
        raise HTTPException(404, "job not found")
    return j


@app.get("/v1/revisions/{revision_id}/chunks")
def list_revision_chunks(revision_id: str) -> dict[str, Any]:
    conn = init_db(config_module.DEFAULT_DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT chunk_business_id, position, start_char, end_char
        FROM chunk_versions WHERE revision_id = ? AND is_current = 1 ORDER BY position
        """,
        (revision_id,),
    )
    rows = cur.fetchall()
    return {
        "revision_id": revision_id,
        "chunks": [
            {"chunk_id": r[0], "position": r[1], "start_char": r[2], "end_char": r[3]}
            for r in rows
        ],
    }


@app.get("/v1/revisions/{revision_id}/latest-analysis")
def get_latest_revision_analysis(revision_id: str) -> dict[str, Any]:
    """Return the most recent run report for this revision, or the latest run on the same document.

    After Save, the editor points at a new revision id before the next full analyze; chunk ids may
    still align with the previous analyzed revision. Falling back to the document's latest run keeps
    the story panel populated until Submit All completes for the new revision.
    """
    conn = init_db(config_module.DEFAULT_DB_PATH)
    rs = RunStore(conn)
    # Prefer a run that has persisted story-wide context; fall back to latest run id.
    run_id = rs.find_latest_run_with_story_map(revision_id) or rs.find_latest_run_for_revision(revision_id)
    from_fallback = False
    if not run_id:
        ds = DocumentStore(conn)
        rev = ds.get_revision(revision_id)
        doc_id = rev.get("document_id") if rev else None
        if doc_id:
            run_id = (
                rs.find_latest_run_for_document_with_story_map(str(doc_id))
                or rs.find_latest_run_for_document(str(doc_id))
            )
            from_fallback = bool(run_id)

    if not run_id:
        return {
            "revision_id": revision_id,
            "run_id": None,
            "report": None,
            "from_fallback": False,
            "run_revision_id": None,
        }

    run_row = rs.get_run_row(run_id) or {}
    chunk_rows = rs.list_chunks_for_run(run_id)
    entries: list[dict[str, Any]] = []
    for row in chunk_rows:
        art = rs.get_chunk_artifact(run_id, row["chunk_id"])
        if not art:
            continue
        judgment = art.get("current_judgment")
        if not isinstance(judgment, dict):
            continue
        entry: dict[str, Any] = {
            "chunk_id": row["chunk_id"],
            "position": row["position"],
            "judgment": judgment,
        }
        cr = art.get("critic_result")
        if isinstance(cr, dict):
            entry["critic_result"] = cr
        dr = art.get("defense_result")
        if isinstance(dr, dict):
            entry["defense_result"] = dr
        entries.append(entry)
    entries.sort(key=lambda e: int(e.get("position", 0)))

    doc_state = rs.get_document_state(run_id)
    document_summary = "Editorial report from narrative analysis."
    if doc_state and doc_state.plot_overview and (doc_state.plot_overview.story_point or "").strip():
        document_summary = f"Story context: {doc_state.plot_overview.story_point.strip()}\n\n{document_summary}"

    story_wide = serialize_story_wide_for_api(doc_state) if doc_state else None

    genre_intention: dict[str, Any] | None = None
    if doc_state and doc_state.genre_intention is not None:
        genre_intention = doc_state.genre_intention.model_dump(mode="json")
    elif run_row.get("genre"):
        g = str(run_row["genre"]).strip()
        if g:
            genre_intention = {
                "genre": g,
                "subgenre_tags": [],
                "tone_descriptors": [],
                "reference_authors": [],
                "short_story_single_chapter": False,
            }

    run_revision_id = run_row.get("revision_id")
    return {
        "revision_id": revision_id,
        "run_id": run_id,
        "analysis_kind": run_row.get("analysis_kind"),
        "from_fallback": from_fallback,
        "run_revision_id": str(run_revision_id) if run_revision_id else None,
        "report": {
            "run_id": run_id,
            "document_summary": document_summary,
            "chunk_judgments": entries,
            "story_wide": story_wide,
            "genre_intention": genre_intention,
        },
    }


@app.get("/v1/runs")
def list_runs(limit: int = 50) -> dict[str, Any]:
    conn = init_db(config_module.DEFAULT_DB_PATH)
    rs = RunStore(conn)
    return {"runs": rs.list_runs(limit=limit)}


@app.get("/v1/documents/{document_id}/bookmarks")
def list_document_bookmarks(document_id: str) -> dict[str, Any]:
    conn = init_db(config_module.DEFAULT_DB_PATH)
    ds = DocumentStore(conn)
    return {"document_id": document_id, "bookmarks": ds.list_bookmarks(document_id)}


@app.post("/v1/documents/{document_id}/bookmarks")
def create_document_bookmark(document_id: str, body: dict[str, Any]) -> dict[str, Any]:
    label = body.get("label")
    revision_id = body.get("revision_id")
    if not label or not isinstance(label, str):
        raise HTTPException(400, "label required")
    if not revision_id or not isinstance(revision_id, str):
        raise HTTPException(400, "revision_id required")
    conn = init_db(config_module.DEFAULT_DB_PATH)
    ds = DocumentStore(conn)
    rev = ds.get_revision(revision_id)
    if not rev or rev["document_id"] != document_id:
        raise HTTPException(404, "revision not found for this document")
    run_id = body.get("run_id")
    if run_id is not None and not isinstance(run_id, str):
        raise HTTPException(400, "run_id must be a string")
    metadata = body.get("metadata")
    if metadata is not None and not isinstance(metadata, dict):
        raise HTTPException(400, "metadata must be an object")
    bid = ds.add_bookmark(
        document_id,
        label,
        revision_id,
        run_id=run_id,
        metadata=metadata,
    )
    return {"bookmark_id": bid, "document_id": document_id}


@app.delete("/v1/bookmarks/{bookmark_id}")
def delete_document_bookmark(bookmark_id: int) -> dict[str, Any]:
    conn = init_db(config_module.DEFAULT_DB_PATH)
    ds = DocumentStore(conn)
    if not ds.delete_bookmark(bookmark_id):
        raise HTTPException(404, "bookmark not found")
    return {"deleted": True, "bookmark_id": bookmark_id}


@app.get("/v1/bookmarks/{bookmark_id}/restore")
def restore_bookmark_session(bookmark_id: int) -> dict[str, Any]:
    conn = init_db(config_module.DEFAULT_DB_PATH)
    ds = DocumentStore(conn)
    rs = RunStore(conn)
    bm = ds.get_bookmark(bookmark_id)
    if not bm:
        raise HTTPException(404, "bookmark not found")
    rev = ds.get_revision(bm["revision_id"])
    if not rev:
        raise HTTPException(404, "revision not found")
    if rev["document_id"] != bm["document_id"]:
        raise HTTPException(404, "bookmark data inconsistent")

    out: dict[str, Any] = {
        "bookmark": bm,
        "revision": rev,
        "run": None,
    }
    rid = bm.get("run_id")
    if rid:
        row = rs.get_run_row(rid)
        if row:
            doc_st = rs.get_document_state(rid)
            out["run"] = {
                **row,
                "has_document_state": doc_st is not None,
                "has_story_map": document_state_has_story_map(doc_st) if doc_st else False,
            }
    return out


@app.post("/v1/chat")
def http_chat(req: ChatRequest, service: NarrativeAnalysisService = Depends(get_service)) -> dict[str, Any]:
    return service.chat(req).model_dump()


@app.get("/v1/revisions/{revision_id}/stream")
async def revision_stream(revision_id: str) -> StreamingResponse:
    """SSE placeholder: emits heartbeat until WebSocket streaming is wired to DAG on_chunk_done."""

    async def gen() -> AsyncIterator[bytes]:
        yield f"data: {json.dumps({'revision_id': revision_id, 'event': 'open'})}\n\n".encode()
        await asyncio.sleep(0.05)
        yield f"data: {json.dumps({'event': 'heartbeat'})}\n\n".encode()

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.websocket("/v1/revisions/{revision_id}/ws")
async def revision_ws(websocket: WebSocket, revision_id: str) -> None:
    await websocket.accept()
    await websocket.send_json({"revision_id": revision_id, "event": "connected"})
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        return


def _install_static_spa_if_configured() -> None:
    """Serve built SPA from EDITR_STATIC_DIR when set; mounted last so /health and /v1/* stay API."""
    raw = (os.getenv("EDITR_STATIC_DIR") or "").strip()
    if not raw:
        return
    root = Path(raw).resolve()
    if not root.is_dir():
        return
    if not (root / "index.html").is_file():
        return
    app.mount("/", StaticFiles(directory=str(root), html=True), name="editr_static")


_install_static_spa_if_configured()
