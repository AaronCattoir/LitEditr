"""Async job records for long-running analysis."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobStore:
    def __init__(self, conn: Any) -> None:
        self._conn = conn

    def create_job(
        self,
        kind: str,
        *,
        document_id: str | None = None,
        revision_id: str | None = None,
        run_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> str:
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
    ) -> None:
        cur = self._conn.cursor()
        cur.execute(
            """
            UPDATE async_jobs
            SET status = ?, result_json = ?, error = ?, run_id = COALESCE(?, run_id), updated_at = ?
            WHERE job_id = ?
            """,
            (
                status,
                json.dumps(result) if result is not None else None,
                error,
                run_id,
                _now(),
                job_id,
            ),
        )
        self._conn.commit()

    def get_job(self, job_id: str) -> dict[str, Any] | None:
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
