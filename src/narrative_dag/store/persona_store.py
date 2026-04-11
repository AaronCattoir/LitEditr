"""SQLite-backed story persona snapshots and events."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class PersonaStore:
    def __init__(self, conn: Any) -> None:
        self._conn = conn

    def next_version(self, document_id: str) -> int:
        cur = self._conn.cursor()
        cur.execute(
            "SELECT COALESCE(MAX(version), 0) + 1 FROM story_persona_snapshots WHERE document_id = ?",
            (document_id,),
        )
        row = cur.fetchone()
        return int(row[0]) if row and row[0] is not None else 1

    def get_latest_snapshot(self, document_id: str) -> dict[str, Any] | None:
        cur = self._conn.cursor()
        cur.execute(
            """
            SELECT id, document_id, revision_id, version, state, deterministic_json, llm_snapshot_json,
                   pet_style_policy_json, soul_seed_path, soul_seed_hash, source_run_id, timbre_delta_json,
                   input_hash, created_at
            FROM story_persona_snapshots
            WHERE document_id = ?
            ORDER BY version DESC
            LIMIT 1
            """,
            (document_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return {
            "id": row[0],
            "document_id": row[1],
            "revision_id": row[2],
            "version": row[3],
            "state": row[4],
            "deterministic_json": json.loads(row[5] or "{}"),
            "llm_snapshot_json": json.loads(row[6]) if row[6] else None,
            "pet_style_policy_json": json.loads(row[7]) if row[7] else None,
            "soul_seed_path": row[8],
            "soul_seed_hash": row[9],
            "source_run_id": row[10],
            "timbre_delta_json": json.loads(row[11]) if row[11] else None,
            "input_hash": row[12],
            "created_at": row[13],
        }

    def insert_snapshot(
        self,
        document_id: str,
        *,
        revision_id: str | None,
        version: int,
        state: str,
        deterministic: dict[str, Any],
        llm_snapshot: dict[str, Any] | None,
        pet_style_policy: dict[str, Any] | None,
        soul_seed_path: str | None,
        soul_seed_hash: str | None,
        source_run_id: str | None,
        timbre_delta: dict[str, Any] | None,
        input_hash: str | None,
    ) -> int:
        cur = self._conn.cursor()
        cur.execute(
            """
            INSERT INTO story_persona_snapshots (
                document_id, revision_id, version, state, deterministic_json, llm_snapshot_json,
                pet_style_policy_json, soul_seed_path, soul_seed_hash, source_run_id, timbre_delta_json,
                input_hash, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                document_id,
                revision_id,
                version,
                state,
                json.dumps(deterministic),
                json.dumps(llm_snapshot) if llm_snapshot is not None else None,
                json.dumps(pet_style_policy) if pet_style_policy is not None else None,
                soul_seed_path,
                soul_seed_hash,
                source_run_id,
                json.dumps(timbre_delta) if timbre_delta is not None else None,
                input_hash,
                _now(),
            ),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def append_event(
        self,
        document_id: str,
        event_type: str,
        source_kind: str,
        *,
        source_id: str | None = None,
        revision_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> int:
        cur = self._conn.cursor()
        cur.execute(
            """
            INSERT INTO story_persona_events (
                document_id, event_type, source_kind, source_id, revision_id, payload_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                document_id,
                event_type,
                source_kind,
                source_id,
                revision_id,
                json.dumps(payload or {}),
                _now(),
            ),
        )
        self._conn.commit()
        return int(cur.lastrowid)
