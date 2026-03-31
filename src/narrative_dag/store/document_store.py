"""Documents, SCD2 revisions, chunk versions, revision events, bookmarks, analytic facts."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from narrative_dag.diffing import sha256_text
from narrative_dag.schemas import Chunk


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class DocumentStore:
    def __init__(self, conn: Any) -> None:
        self._conn = conn

    def document_exists(self, document_id: str) -> bool:
        cur = self._conn.cursor()
        cur.execute("SELECT 1 FROM documents WHERE document_id = ?", (document_id,))
        return cur.fetchone() is not None

    def create_document(
        self,
        title: str | None = None,
        author: str | None = None,
        writer_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        document_id = str(uuid.uuid4())
        cur = self._conn.cursor()
        cur.execute(
            """
            INSERT INTO documents (document_id, title, author, writer_id, created_at, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                document_id,
                title or "",
                author or "",
                writer_id or "",
                _now(),
                json.dumps(metadata or {}),
            ),
        )
        self._conn.commit()
        return document_id

    def create_revision(
        self,
        document_id: str,
        full_text: str,
        *,
        parent_revision_id: str | None = None,
        branch_name: str | None = None,
        diff_summary: dict[str, Any] | None = None,
    ) -> str:
        revision_id = str(uuid.uuid4())
        h = sha256_text(full_text)
        cur = self._conn.cursor()
        cur.execute(
            "SELECT revision_id, root_revision_id FROM document_revisions WHERE document_id = ? AND is_current = 1",
            (document_id,),
        )
        parent_row = cur.fetchone()
        parent = parent_revision_id
        if parent is None and parent_row:
            parent = parent_row[0]
        if parent_row and parent_row[1]:
            root = parent_row[1]
        elif parent_row:
            root = parent_row[0]
        else:
            root = revision_id

        cur.execute(
            "UPDATE document_revisions SET is_current = 0, valid_to = ? WHERE document_id = ? AND is_current = 1",
            (_now(), document_id),
        )
        cur.execute(
            """
            INSERT INTO document_revisions (
                revision_id, document_id, parent_revision_id, root_revision_id, branch_name,
                text_hash, full_text, byte_length, diff_summary_json,
                valid_from, valid_to, is_current, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
            """,
            (
                revision_id,
                document_id,
                parent,
                root,
                branch_name or "",
                h,
                full_text,
                len(full_text.encode("utf-8")),
                json.dumps(diff_summary) if diff_summary else None,
                _now(),
                None,
                _now(),
            ),
        )
        self._conn.commit()
        return revision_id

    def get_revision(self, revision_id: str) -> dict[str, Any] | None:
        cur = self._conn.cursor()
        cur.execute(
            "SELECT revision_id, document_id, full_text, text_hash, created_at, is_current FROM document_revisions WHERE revision_id = ?",
            (revision_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return {
            "revision_id": row[0],
            "document_id": row[1],
            "full_text": row[2],
            "text_hash": row[3],
            "created_at": row[4],
            "is_current": bool(row[5]),
        }

    def list_revisions(self, document_id: str, limit: int = 100) -> list[dict[str, Any]]:
        cur = self._conn.cursor()
        cur.execute(
            """
            SELECT revision_id, parent_revision_id, text_hash, created_at, is_current, byte_length
            FROM document_revisions
            WHERE document_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (document_id, limit),
        )
        out = []
        for row in cur.fetchall():
            out.append(
                {
                    "revision_id": row[0],
                    "parent_revision_id": row[1],
                    "text_hash": row[2],
                    "created_at": row[3],
                    "is_current": bool(row[4]),
                    "byte_length": row[5],
                }
            )
        return out

    def replace_chunk_versions(self, revision_id: str, chunks: list[Chunk]) -> None:
        """Close prior chunk rows and insert current spans for this revision."""
        cur = self._conn.cursor()
        ts = _now()
        cur.execute(
            "UPDATE chunk_versions SET is_current = 0, valid_to = ? WHERE revision_id = ? AND is_current = 1",
            (ts, revision_id),
        )
        for ch in chunks:
            cur.execute(
                """
                INSERT INTO chunk_versions (
                    revision_id, chunk_business_id, position, start_char, end_char,
                    valid_from, valid_to, is_current
                )
                VALUES (?, ?, ?, ?, ?, ?, NULL, 1)
                """,
                (revision_id, ch.id, ch.position, ch.start_char, ch.end_char, ts),
            )
        self._conn.commit()

    def get_chunk_version_map(self, revision_id: str) -> dict[str, int]:
        """Map chunk_business_id -> chunk_versions.id for current rows."""
        cur = self._conn.cursor()
        cur.execute(
            """
            SELECT id, chunk_business_id FROM chunk_versions
            WHERE revision_id = ? AND is_current = 1
            """,
            (revision_id,),
        )
        return {row[1]: row[0] for row in cur.fetchall()}

    def get_revision_chunk_text(self, revision_id: str, chunk_business_id: str) -> str | None:
        """Slice current revision full_text using chunk_versions span; None if missing."""
        rev = self.get_revision(revision_id)
        if not rev:
            return None
        full = rev.get("full_text") or ""
        cur = self._conn.cursor()
        cur.execute(
            """
            SELECT start_char, end_char FROM chunk_versions
            WHERE revision_id = ? AND chunk_business_id = ? AND is_current = 1
            LIMIT 1
            """,
            (revision_id, chunk_business_id),
        )
        row = cur.fetchone()
        if not row:
            return None
        start, end = int(row[0]), int(row[1])
        if start < 0 or end < start or end > len(full):
            return None
        return full[start:end]

    def record_revision_event(
        self,
        document_id: str,
        to_revision_id: str,
        event_type: str,
        *,
        from_revision_id: str | None = None,
        actor_id: str | None = None,
        reason: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        cur = self._conn.cursor()
        cur.execute(
            """
            INSERT INTO revision_events (
                document_id, from_revision_id, to_revision_id, event_type, actor_id, reason, metadata_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                document_id,
                from_revision_id,
                to_revision_id,
                event_type,
                actor_id or "",
                reason or "",
                json.dumps(metadata or {}),
                _now(),
            ),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def add_bookmark(
        self,
        document_id: str,
        label: str,
        revision_id: str,
        *,
        run_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        cur = self._conn.cursor()
        cur.execute(
            """
            INSERT INTO user_bookmarks (document_id, label, revision_id, run_id, metadata_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                document_id,
                label,
                revision_id,
                run_id,
                json.dumps(metadata or {}),
                _now(),
            ),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def list_bookmarks(self, document_id: str) -> list[dict[str, Any]]:
        cur = self._conn.cursor()
        cur.execute(
            """
            SELECT id, document_id, label, revision_id, run_id, metadata_json, created_at
            FROM user_bookmarks WHERE document_id = ? ORDER BY created_at DESC
            """,
            (document_id,),
        )
        out = []
        for row in cur.fetchall():
            meta_raw = row[5]
            try:
                meta = json.loads(meta_raw) if meta_raw else {}
            except json.JSONDecodeError:
                meta = {}
            out.append(
                {
                    "id": row[0],
                    "document_id": row[1],
                    "label": row[2],
                    "revision_id": row[3],
                    "run_id": row[4],
                    "metadata": meta,
                    "created_at": row[6],
                }
            )
        return out

    def get_bookmark(self, bookmark_id: int) -> dict[str, Any] | None:
        cur = self._conn.cursor()
        cur.execute(
            """
            SELECT id, document_id, label, revision_id, run_id, metadata_json, created_at
            FROM user_bookmarks WHERE id = ?
            """,
            (bookmark_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        meta_raw = row[5]
        try:
            meta = json.loads(meta_raw) if meta_raw else {}
        except json.JSONDecodeError:
            meta = {}
        return {
            "id": row[0],
            "document_id": row[1],
            "label": row[2],
            "revision_id": row[3],
            "run_id": row[4],
            "metadata": meta,
            "created_at": row[6],
        }

    def delete_bookmark(self, bookmark_id: int) -> bool:
        cur = self._conn.cursor()
        cur.execute("DELETE FROM user_bookmarks WHERE id = ?", (bookmark_id,))
        self._conn.commit()
        return cur.rowcount > 0

    def get_current_revision_for_document(self, document_id: str) -> dict[str, Any] | None:
        cur = self._conn.cursor()
        cur.execute(
            """
            SELECT revision_id, document_id, full_text, text_hash, created_at, is_current
            FROM document_revisions WHERE document_id = ? AND is_current = 1 LIMIT 1
            """,
            (document_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return {
            "revision_id": row[0],
            "document_id": row[1],
            "full_text": row[2],
            "text_hash": row[3],
            "created_at": row[4],
            "is_current": bool(row[5]),
        }

    def list_document_chapters(self, document_id: str) -> list[dict[str, Any]]:
        cur = self._conn.cursor()
        cur.execute(
            """
            SELECT chapter_id, document_id, title, sort_order, created_at
            FROM document_chapters WHERE document_id = ?
            ORDER BY sort_order ASC, created_at ASC
            """,
            (document_id,),
        )
        return [
            {
                "chapter_id": r[0],
                "document_id": r[1],
                "title": r[2],
                "sort_order": r[3],
                "created_at": r[4],
            }
            for r in cur.fetchall()
        ]

    def create_document_chapter(
        self,
        document_id: str,
        title: str,
        *,
        sort_order: int | None = None,
    ) -> str:
        chapter_id = str(uuid.uuid4())
        cur = self._conn.cursor()
        if sort_order is None:
            cur.execute(
                "SELECT COALESCE(MAX(sort_order), -1) + 1 FROM document_chapters WHERE document_id = ?",
                (document_id,),
            )
            sort_order = int(cur.fetchone()[0])
        cur.execute(
            """
            INSERT INTO document_chapters (chapter_id, document_id, title, sort_order, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (chapter_id, document_id, title or "", sort_order, _now()),
        )
        self._conn.commit()
        return chapter_id

    def update_document_chapter(
        self,
        chapter_id: str,
        *,
        title: str | None = None,
        sort_order: int | None = None,
    ) -> bool:
        cur = self._conn.cursor()
        cur.execute(
            "SELECT chapter_id FROM document_chapters WHERE chapter_id = ?",
            (chapter_id,),
        )
        if not cur.fetchone():
            return False
        if title is not None:
            cur.execute(
                "UPDATE document_chapters SET title = ? WHERE chapter_id = ?",
                (title, chapter_id),
            )
        if sort_order is not None:
            cur.execute(
                "UPDATE document_chapters SET sort_order = ? WHERE chapter_id = ?",
                (sort_order, chapter_id),
            )
        self._conn.commit()
        return True

    def delete_document_chapter(self, chapter_id: str) -> bool:
        cur = self._conn.cursor()
        cur.execute("DELETE FROM document_chapters WHERE chapter_id = ?", (chapter_id,))
        self._conn.commit()
        return cur.rowcount > 0

    def get_document_id_for_chapter(self, chapter_id: str) -> str | None:
        cur = self._conn.cursor()
        cur.execute(
            "SELECT document_id FROM document_chapters WHERE chapter_id = ?",
            (chapter_id,),
        )
        row = cur.fetchone()
        return str(row[0]) if row else None

    def save_analytic_fact(
        self,
        analysis_run_id: str,
        revision_id: str,
        fact_kind: str,
        payload: dict[str, Any],
        chunk_version_id: int | None = None,
    ) -> None:
        cur = self._conn.cursor()
        cur.execute(
            """
            INSERT INTO analytic_facts (analysis_run_id, revision_id, chunk_version_id, fact_kind, payload_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (analysis_run_id, revision_id, chunk_version_id, fact_kind, json.dumps(payload), _now()),
        )
        self._conn.commit()
