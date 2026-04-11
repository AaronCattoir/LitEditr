"""Async job records for long-running analysis."""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobStore:
    """SQLite async_jobs; serialize access — same connection is used from API threads and background analyze."""

    def __init__(self, conn: Any) -> None:
        self._conn = conn
        self._lock = threading.RLock()

    def create_job(
        self,
        kind: str,
        *,
        document_id: str | None = None,
        revision_id: str | None = None,
        run_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> str:
        with self._lock:
            job_id = str(uuid.uuid4())
            cur = self._conn.cursor()
            ts = _now()
            cur.execute(
                """
                INSERT INTO async_jobs (job_id, kind, status, document_id, revision_id, run_id, payload_json, created_at, updated_at)
                VALUES (?, ?, 'queued', ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    kind,
                    document_id,
                    revision_id,
                    run_id,
                    json.dumps(payload or {}),
                    ts,
                    ts,
                ),
            )
            self._conn.commit()
            return job_id

    def update_job(
        self,
        job_id: str,
        status: str,
        *,
        result: dict[str, Any] | None = None,
        error: str | None = None,
        run_id: str | None = None,
        input_hash: str | None = None,
        output_persona_version: int | None = None,
    ) -> None:
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                """
                UPDATE async_jobs
                SET status = ?, result_json = ?, error = ?, run_id = COALESCE(?, run_id),
                    input_hash = COALESCE(?, input_hash),
                    output_persona_version = COALESCE(?, output_persona_version),
                    updated_at = ?
                WHERE job_id = ?
                """,
                (
                    status,
                    json.dumps(result) if result is not None else None,
                    error,
                    run_id,
                    input_hash,
                    output_persona_version,
                    _now(),
                    job_id,
                ),
            )
            self._conn.commit()

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                """
                SELECT job_id, kind, status, document_id, revision_id, run_id, payload_json, result_json, error, created_at, updated_at
                FROM async_jobs WHERE job_id = ?
                """,
                (job_id,),
            )
            row = cur.fetchone()
            if not row:
                return None
            return {
                "job_id": row[0],
                "kind": row[1],
                "status": row[2],
                "document_id": row[3],
                "revision_id": row[4],
                "run_id": row[5],
                "payload": json.loads(row[6] or "{}"),
                "result": json.loads(row[7]) if row[7] else None,
                "error": row[8],
                "created_at": row[9],
                "updated_at": row[10],
            }

    def find_active_analyze_job_for_revision(self, revision_id: str) -> str | None:
        """Return job_id of a queued or running analyze job for this revision, if any."""
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                """
                SELECT job_id FROM async_jobs
                WHERE kind = 'analyze' AND revision_id = ? AND status IN ('queued', 'running')
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (revision_id,),
            )
            row = cur.fetchone()
            return row[0] if row else None

    def find_succeeded_persona_job(
        self, document_id: str, revision_id: str, source_run_id: str
    ) -> bool:
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                """
                SELECT 1 FROM async_jobs
                WHERE kind = 'persona_refresh' AND status = 'succeeded'
                AND document_id = ? AND revision_id = ? AND run_id = ?
                LIMIT 1
                """,
                (document_id, revision_id, source_run_id),
            )
            return cur.fetchone() is not None

    def find_active_persona_job_for_run(
        self, document_id: str, revision_id: str, run_id: str
    ) -> str | None:
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                """
                SELECT job_id FROM async_jobs
                WHERE kind = 'persona_refresh' AND revision_id = ? AND run_id = ?
                AND document_id = ? AND status IN ('queued', 'running')
                ORDER BY created_at DESC LIMIT 1
                """,
                (revision_id, run_id, document_id),
            )
            row = cur.fetchone()
            return str(row[0]) if row else None

    def has_pending_persona_refresh(self, document_id: str) -> bool:
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                """
                SELECT 1 FROM async_jobs
                WHERE kind = 'persona_refresh' AND document_id = ?
                AND status IN ('queued', 'running')
                LIMIT 1
                """,
                (document_id,),
            )
            return cur.fetchone() is not None
