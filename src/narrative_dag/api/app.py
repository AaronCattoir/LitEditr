"""FastAPI application: documents, revisions, async jobs, chat, SSE progress stream."""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from narrative_dag.config import DEFAULT_DB_PATH
from narrative_dag.contracts import AnalyzeDocumentRequest, ChatRequest
from narrative_dag.db import init_db
from narrative_dag.service import NarrativeAnalysisService
from narrative_dag.store.document_store import DocumentStore
from narrative_dag.store.job_store import JobStore
from narrative_dag.store.run_store import RunStore

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
        conn = init_db(DEFAULT_DB_PATH)
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


@app.post("/v1/documents")
def create_document(
    title: str | None = None,
    author: str | None = None,
) -> dict[str, Any]:
    conn = init_db(DEFAULT_DB_PATH)
    ds = DocumentStore(conn)
    doc_id = ds.create_document(title=title, author=author)
    return {"document_id": doc_id}


@app.post("/v1/documents/{document_id}/revisions")
def submit_revision(document_id: str, body: dict[str, Any]) -> dict[str, Any]:
    text = body.get("text") or body.get("document_text")
    if not text or not isinstance(text, str):
        raise HTTPException(400, "text or document_text required")
    conn = init_db(DEFAULT_DB_PATH)
    ds = DocumentStore(conn)
    parent = body.get("parent_revision_id")
    rid = ds.create_revision(document_id, text, parent_revision_id=parent)
    ds.record_revision_event(document_id, rid, "submit", from_revision_id=parent)
    return {"revision_id": rid, "document_id": document_id}


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
    conn = init_db(DEFAULT_DB_PATH)
    ds = DocumentStore(conn)
    rev = ds.get_revision(revision_id)
    if not rev:
        raise HTTPException(404, "revision not found")
    text = rev.get("full_text") or ""
    genre = body.get("genre") or "literary_fiction"
    job_store = get_job_store()
    payload = {
        "document_text": text,
        "genre": genre,
        "subgenre_tags": body.get("subgenre_tags") or [],
        "tone_descriptors": body.get("tone_descriptors") or [],
        "reference_authors": body.get("reference_authors") or [],
        "title": body.get("title"),
        "author": body.get("author"),
        "document_id": rev["document_id"],
        "revision_id": revision_id,
    }
    job_id = job_store.create_job(
        "analyze",
        document_id=rev["document_id"],
        revision_id=revision_id,
        payload=payload,
    )
    background_tasks.add_task(_run_analyze_job, job_id, payload)
    return JSONResponse({"job_id": job_id, "status": "queued"}, status_code=202)


@app.get("/v1/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    j = get_job_store().get_job(job_id)
    if not j:
        raise HTTPException(404, "job not found")
    return j


@app.get("/v1/revisions/{revision_id}/chunks")
def list_revision_chunks(revision_id: str) -> dict[str, Any]:
    conn = init_db(DEFAULT_DB_PATH)
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


@app.get("/v1/runs")
def list_runs(limit: int = 50) -> dict[str, Any]:
    conn = init_db(DEFAULT_DB_PATH)
    rs = RunStore(conn)
    return {"runs": rs.list_runs(limit=limit)}


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
