"""SQLite-backed JudgmentStore: immutable judgment versions keyed by run_id + chunk_id."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from narrative_dag.schemas import EditorJudgment, JudgmentVersion


class JudgmentStore:
    """SQLite-backed immutable judgment versions keyed by run_id + chunk_id."""

    def __init__(self, conn: Any) -> None:
        self._conn = conn

    def save_judgment(
        self,
        run_id: str,
        chunk_id: str,
        judgment: EditorJudgment,
        source: str,
        rationale: str = "",
    ) -> JudgmentVersion:
        cur = self._conn.cursor()
        cur.execute(
            "SELECT COALESCE(MAX(version), 0) FROM judgment_versions WHERE run_id = ? AND chunk_id = ?",
            (run_id, chunk_id),
        )
        version = cur.fetchone()[0] + 1
        now = datetime.now(timezone.utc).isoformat()
        cur.execute(
            """
            INSERT INTO judgment_versions (run_id, chunk_id, version, judgment_json, source, rationale, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (run_id, chunk_id, version, judgment.model_dump_json(), source, rationale, now),
        )
        self._conn.commit()
        return JudgmentVersion(
            chunk_id=chunk_id,
            run_id=run_id,
            version=version,
            judgment=judgment,
            source=source,
            rationale_for_change=rationale,
        )

    def get_latest_judgment(self, run_id: str, chunk_id: str) -> JudgmentVersion | None:
        cur = self._conn.cursor()
        cur.execute(
            """
            SELECT judgment_json, version, source, rationale
            FROM judgment_versions
            WHERE run_id = ? AND chunk_id = ?
            ORDER BY version DESC LIMIT 1
            """,
            (run_id, chunk_id),
        )
        row = cur.fetchone()
        if not row:
            return None
        judgment = EditorJudgment.model_validate_json(row[0])
        return JudgmentVersion(
            chunk_id=chunk_id,
            run_id=run_id,
            version=row[1],
            judgment=judgment,
            source=row[2] or "editor_judge",
            rationale_for_change=row[3] or "",
        )

    def get_judgment_history(self, run_id: str, chunk_id: str) -> list[JudgmentVersion]:
        cur = self._conn.cursor()
        cur.execute(
            """
            SELECT judgment_json, version, source, rationale
            FROM judgment_versions
            WHERE run_id = ? AND chunk_id = ?
            ORDER BY version ASC
            """,
            (run_id, chunk_id),
        )
        out = []
        for row in cur.fetchall():
            judgment = EditorJudgment.model_validate_json(row[0])
            out.append(
                JudgmentVersion(
                    chunk_id=chunk_id,
                    run_id=run_id,
                    version=row[1],
                    judgment=judgment,
                    source=row[2] or "editor_judge",
                    rationale_for_change=row[3] or "",
                )
            )
        return out
