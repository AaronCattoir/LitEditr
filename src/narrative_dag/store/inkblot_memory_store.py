"""Document-scoped Inkblot writer memory (goals, emotions, session summaries)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class InkblotMemoryStore:
    def __init__(self, conn: Any) -> None:
        self._conn = conn

    def get_payload(self, document_id: str) -> dict[str, Any]:
        cur = self._conn.cursor()
        cur.execute(
            "SELECT payload_json, updated_at FROM story_inkblot_memory WHERE document_id = ?",
            (document_id,),
        )
        row = cur.fetchone()
        if not row:
            return {}
        try:
            return json.loads(row[0] or "{}")
        except json.JSONDecodeError:
            return {}

    def get_row(self, document_id: str) -> dict[str, Any] | None:
        cur = self._conn.cursor()
        cur.execute(
            "SELECT document_id, payload_json, updated_at FROM story_inkblot_memory WHERE document_id = ?",
            (document_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        try:
            payload = json.loads(row[1] or "{}")
        except json.JSONDecodeError:
            payload = {}
        return {"document_id": row[0], "payload": payload, "updated_at": row[2]}

    def upsert_payload(self, document_id: str, payload: dict[str, Any]) -> None:
        ts = _now()
        cur = self._conn.cursor()
        cur.execute(
            """
            INSERT INTO story_inkblot_memory (document_id, payload_json, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(document_id) DO UPDATE SET
                payload_json = excluded.payload_json,
                updated_at = excluded.updated_at
            """,
            (document_id, json.dumps(payload), ts),
        )
        self._conn.commit()

    def merge_payload(self, document_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        base = self.get_payload(document_id)
        merged = {**base, **patch}
        self.upsert_payload(document_id, merged)
        return merged
