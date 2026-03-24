"""SQLite-backed RunStore: run metadata, chunk artifacts, document state."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from narrative_dag.db import get_connection
from narrative_dag.schemas import (
    Chunk,
    ContextBundle,
    ContextWindow,
    CriticResult,
    DefenseResult,
    DocumentState,
    EditorJudgment,
    GenreIntention,
)


def _serialize(obj: Any) -> str:
    if hasattr(obj, "model_dump"):
        return json.dumps(obj.model_dump())
    return json.dumps(obj)


def _doc_state_from_dict(d: dict[str, Any]) -> DocumentState:
    return DocumentState.model_validate(d)


class RunStore:
    """SQLite implementation of RunStoreInterface."""

    def __init__(self, conn: Any) -> None:
        self._conn = conn

    def save_run_meta(
        self,
        run_id: str,
        genre: str | None = None,
        title: str | None = None,
        author: str | None = None,
        *,
        document_id: str | None = None,
        revision_id: str | None = None,
        analysis_kind: str = "full",
    ) -> None:
        cur = self._conn.cursor()
        now = datetime.now(timezone.utc).isoformat()
        cur.execute(
            """
            INSERT OR REPLACE INTO runs (
                run_id, created_at, genre, document_title, document_author, metadata_json,
                document_id, revision_id, analysis_kind
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                now,
                genre or "",
                title or "",
                author or "",
                "{}",
                document_id,
                revision_id,
                analysis_kind,
            ),
        )
        self._conn.commit()

    def list_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        cur = self._conn.cursor()
        cur.execute(
            """
            SELECT run_id, created_at, genre, document_title, document_author, document_id, revision_id, analysis_kind
            FROM runs
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = cur.fetchall()
        return [
            {
                "run_id": r[0],
                "created_at": r[1],
                "genre": r[2],
                "document_title": r[3],
                "document_author": r[4],
                "document_id": r[5],
                "revision_id": r[6],
                "analysis_kind": r[7],
            }
            for r in rows
        ]

    def list_chunks_for_run(self, run_id: str) -> list[dict[str, Any]]:
        cur = self._conn.cursor()
        cur.execute(
            "SELECT chunk_id, position FROM run_chunks WHERE run_id = ? ORDER BY position ASC",
            (run_id,),
        )
        return [{"chunk_id": r[0], "position": r[1]} for r in cur.fetchall()]

    def save_chunk_artifact(self, run_id: str, chunk_id: str, position: int, payload: dict[str, Any]) -> None:
        cur = self._conn.cursor()
        cur.execute(
            """
            INSERT OR REPLACE INTO run_chunks (run_id, chunk_id, position, payload_json)
            VALUES (?, ?, ?, ?)
            """,
            (run_id, chunk_id, position, json.dumps(payload)),
        )
        self._conn.commit()

    def save_document_state(self, run_id: str, state: DocumentState) -> None:
        cur = self._conn.cursor()
        payload = state.model_dump()
        cur.execute(
            """
            INSERT OR REPLACE INTO run_document_state (run_id, payload_json)
            VALUES (?, ?)
            """,
            (run_id, json.dumps(payload)),
        )
        self._conn.commit()

    def get_chunk_artifact(self, run_id: str, chunk_id: str) -> dict[str, Any] | None:
        cur = self._conn.cursor()
        cur.execute("SELECT payload_json FROM run_chunks WHERE run_id = ? AND chunk_id = ?", (run_id, chunk_id))
        row = cur.fetchone()
        if not row:
            return None
        return json.loads(row[0])

    def get_document_state(self, run_id: str) -> DocumentState | None:
        cur = self._conn.cursor()
        cur.execute("SELECT payload_json FROM run_document_state WHERE run_id = ?", (run_id,))
        row = cur.fetchone()
        if not row:
            return None
        return _doc_state_from_dict(json.loads(row[0]))

    def get_context_bundle(self, run_id: str, chunk_id: str) -> ContextBundle | None:
        artifact = self.get_chunk_artifact(run_id, chunk_id)
        if not artifact:
            return None
        doc_state = self.get_document_state(run_id)
        if not doc_state:
            doc_state = DocumentState()

        def _chunk(d: dict) -> Chunk:
            return Chunk.model_validate(d)

        target_chunk = _chunk(artifact["target_chunk"])
        ctx = artifact.get("context_window")
        if ctx:
            context_window = ContextWindow(
                target_chunk=_chunk(ctx["target_chunk"]),
                previous_chunks=[_chunk(c) for c in ctx.get("previous_chunks", [])],
                next_chunks=[_chunk(c) for c in ctx.get("next_chunks", [])],
                global_summary=ctx.get("global_summary", ""),
            )
        else:
            context_window = ContextWindow(target_chunk=target_chunk)

        genre = doc_state.genre_intention if isinstance(doc_state.genre_intention, GenreIntention) else None
        if not genre and isinstance(doc_state.genre_intention, dict):
            genre = GenreIntention.model_validate(doc_state.genre_intention)

        raw_judgment = artifact.get("current_judgment")
        current_judgment = None
        if raw_judgment is not None:
            current_judgment = EditorJudgment.model_validate(raw_judgment) if isinstance(raw_judgment, dict) else raw_judgment
        raw_critic = artifact.get("critic_result")
        critic_result = CriticResult.model_validate(raw_critic) if isinstance(raw_critic, dict) else raw_critic
        raw_defense = artifact.get("defense_result")
        defense_result = DefenseResult.model_validate(raw_defense) if isinstance(raw_defense, dict) else raw_defense

        return ContextBundle(
            target_chunk=target_chunk,
            context_window=context_window,
            document_state=doc_state,
            detector_results=artifact.get("detector_results", {}),
            critic_result=critic_result,
            defense_result=defense_result,
            current_judgment=current_judgment,
            genre_intention=genre,
        )
