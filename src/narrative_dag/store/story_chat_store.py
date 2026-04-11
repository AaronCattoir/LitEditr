"""Story-scoped chat sessions and turns (inkblot)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class StoryChatStore:
    def __init__(self, conn: Any) -> None:
        self._conn = conn

    def create_session(
        self,
        document_id: str,
        *,
        revision_id: str | None = None,
        persona_version: int | None = None,
    ) -> str:
        session_id = str(uuid.uuid4())
        ts = _now()
        cur = self._conn.cursor()
        cur.execute(
            """
            INSERT INTO story_chat_sessions (session_id, document_id, revision_id, persona_version, session_summary, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (session_id, document_id, revision_id, persona_version, "", ts, ts),
        )
        self._conn.commit()
        return session_id

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        cur = self._conn.cursor()
        cur.execute(
            """
            SELECT session_id, document_id, revision_id, persona_version, session_summary, created_at, updated_at
            FROM story_chat_sessions WHERE session_id = ?
            """,
            (session_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return {
            "session_id": row[0],
            "document_id": row[1],
            "revision_id": row[2],
            "persona_version": row[3],
            "session_summary": row[4] or "",
            "created_at": row[5],
            "updated_at": row[6],
        }

    def list_sessions(self, document_id: str, limit: int = 50) -> list[dict[str, Any]]:
        cur = self._conn.cursor()
        cur.execute(
            """
            SELECT session_id, document_id, revision_id, persona_version, created_at, updated_at
            FROM story_chat_sessions WHERE document_id = ?
            ORDER BY updated_at DESC LIMIT ?
            """,
            (document_id, limit),
        )
        out = []
        for r in cur.fetchall():
            out.append(
                {
                    "session_id": r[0],
                    "document_id": r[1],
                    "revision_id": r[2],
                    "persona_version": r[3],
                    "created_at": r[4],
                    "updated_at": r[5],
                }
            )
        return out

    def update_session(
        self,
        session_id: str,
        *,
        revision_id: str | None = None,
        persona_version: int | None = None,
        session_summary: str | None = None,
    ) -> None:
        cur = self._conn.cursor()
        cur.execute(
            "SELECT document_id FROM story_chat_sessions WHERE session_id = ?",
            (session_id,),
        )
        if not cur.fetchone():
            return
        sets = ["updated_at = ?"]
        params: list[Any] = [_now()]
        if revision_id is not None:
            sets.append("revision_id = ?")
            params.append(revision_id)
        if persona_version is not None:
            sets.append("persona_version = ?")
            params.append(persona_version)
        if session_summary is not None:
            sets.append("session_summary = ?")
            params.append(session_summary)
        params.append(session_id)
        cur.execute(
            f"UPDATE story_chat_sessions SET {', '.join(sets)} WHERE session_id = ?",
            params,
        )
        self._conn.commit()

    def next_turn_index(self, session_id: str) -> int:
        cur = self._conn.cursor()
        cur.execute(
            "SELECT COALESCE(MAX(turn_index), -1) + 1 FROM story_chat_turns WHERE session_id = ?",
            (session_id,),
        )
        row = cur.fetchone()
        return int(row[0]) if row and row[0] is not None else 0

    def append_turn(
        self,
        session_id: str,
        *,
        role: str,
        content: str,
        context_manifest: dict[str, Any] | None = None,
    ) -> int:
        idx = self.next_turn_index(session_id)
        cur = self._conn.cursor()
        cur.execute(
            """
            INSERT INTO story_chat_turns (session_id, turn_index, role, content, context_manifest_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                idx,
                role,
                content,
                json.dumps(context_manifest or {}),
                _now(),
            ),
        )
        self._conn.commit()
        cur.execute(
            "UPDATE story_chat_sessions SET updated_at = ? WHERE session_id = ?",
            (_now(), session_id),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def list_turns(self, session_id: str) -> list[dict[str, Any]]:
        cur = self._conn.cursor()
        cur.execute(
            """
            SELECT turn_index, role, content, context_manifest_json, created_at
            FROM story_chat_turns WHERE session_id = ?
            ORDER BY turn_index ASC
            """,
            (session_id,),
        )
        out = []
        for r in cur.fetchall():
            raw = r[3]
            try:
                manifest = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                manifest = {}
            out.append(
                {
                    "turn_index": r[0],
                    "role": r[1],
                    "content": r[2],
                    "context_manifest": manifest,
                    "created_at": r[4],
                }
            )
        return out

    def recent_turns_for_prompt(self, session_id: str, max_turns: int) -> list[dict[str, Any]]:
        all_turns = self.list_turns(session_id)
        if len(all_turns) <= max_turns:
            return all_turns
        return all_turns[-max_turns:]
