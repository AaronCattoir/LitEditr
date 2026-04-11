"""SQLite-backed RunStore: run metadata, chunk artifacts, document state."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

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


def document_state_has_story_map(ds: DocumentState) -> bool:
    """True if persisted document state has enough global story context for quick coach."""
    po = ds.plot_overview
    if po:
        if (po.story_point or "").strip() or (po.plot_summary or "").strip():
            return True
    cdb = ds.character_database
    if cdb and cdb.characters:
        return True
    return False


def _serialize(obj: Any) -> str:
    if hasattr(obj, "model_dump"):
        return json.dumps(obj.model_dump())
    return json.dumps(obj)


def _doc_state_from_dict(d: dict[str, Any]) -> DocumentState:
    return DocumentState.model_validate(d)


def serialize_story_wide_for_api(ds: DocumentState) -> dict[str, Any]:
    """JSON-serializable story-wide fields from persisted run document_state."""
    po = ds.plot_overview
    cdb = ds.character_database
    vb: Any = ds.voice_baseline
    if hasattr(vb, "model_dump"):
        vb = vb.model_dump(mode="json")
    return {
        "plot_overview": po.model_dump(mode="json") if po is not None else None,
        "character_database": cdb.model_dump(mode="json") if cdb is not None else None,
        "narrative_map": list(ds.narrative_map),
        "emotional_curve": list(ds.emotional_curve),
        "voice_baseline": vb,
    }


class RunStore:
    """SQLite-backed persistence for run metadata, chunk artifacts, and document state."""

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

    def get_revision_id_for_run(self, run_id: str) -> str | None:
        cur = self._conn.cursor()
        cur.execute("SELECT revision_id FROM runs WHERE run_id = ?", (run_id,))
        row = cur.fetchone()
        if not row or row[0] is None:
            return None
        return str(row[0])

    def find_latest_run_with_story_map(self, revision_id: str) -> str | None:
        """Latest full run for revision that has run_document_state + story map content."""
        cur = self._conn.cursor()
        cur.execute(
            """
            SELECT r.run_id FROM runs r
            INNER JOIN run_document_state rds ON r.run_id = rds.run_id
            WHERE r.revision_id = ?
            AND (r.analysis_kind IN ('full', 'partial') OR r.analysis_kind IS NULL)
            ORDER BY r.created_at DESC
            """,
            (revision_id,),
        )
        for (run_id,) in cur.fetchall():
            ds = self.get_document_state(run_id)
            if ds and document_state_has_story_map(ds):
                return run_id
        return None

    def find_latest_run_for_revision(self, revision_id: str) -> str | None:
        """Latest run id for a revision, regardless of story-map completeness."""
        cur = self._conn.cursor()
        cur.execute(
            """
            SELECT run_id
            FROM runs
            WHERE revision_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (revision_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return str(row[0])

    def find_latest_run_for_document(self, document_id: str) -> str | None:
        """Latest run for any revision of this document (same manuscript lineage)."""
        cur = self._conn.cursor()
        cur.execute(
            """
            SELECT run_id
            FROM runs
            WHERE document_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (document_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return str(row[0])

    def find_latest_run_for_document_with_story_map(self, document_id: str) -> str | None:
        """Latest full/partial run on a document that has usable story-wide context."""
        cur = self._conn.cursor()
        cur.execute(
            """
            SELECT r.run_id FROM runs r
            INNER JOIN run_document_state rds ON r.run_id = rds.run_id
            WHERE r.document_id = ?
            AND (r.analysis_kind IN ('full', 'partial') OR r.analysis_kind IS NULL)
            ORDER BY r.created_at DESC
            """,
            (document_id,),
        )
        for (run_id,) in cur.fetchall():
            ds = self.get_document_state(run_id)
            if ds and document_state_has_story_map(ds):
                return run_id
        return None

    def get_run_row(self, run_id: str) -> dict[str, Any] | None:
        cur = self._conn.cursor()
        cur.execute(
            """
            SELECT run_id, created_at, genre, document_title, document_author, document_id, revision_id, analysis_kind
            FROM runs WHERE run_id = ?
            """,
            (run_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return {
            "run_id": row[0],
            "created_at": row[1],
            "genre": row[2],
            "document_title": row[3],
            "document_author": row[4],
            "document_id": row[5],
            "revision_id": row[6],
            "analysis_kind": row[7],
        }

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

    def has_chunk_artifact(self, run_id: str, chunk_id: str) -> bool:
        cur = self._conn.cursor()
        cur.execute(
            "SELECT 1 FROM run_chunks WHERE run_id = ? AND chunk_id = ? LIMIT 1",
            (run_id, chunk_id),
        )
        return cur.fetchone() is not None

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
