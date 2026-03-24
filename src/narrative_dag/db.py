"""SQLite engine/session setup and migration bootstrap."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from narrative_dag.migration import add_column_if_missing


def get_connection(db_path: str) -> sqlite3.Connection:
    """Return a connection to the SQLite database; creates file if needed."""
    if db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys = ON")
    except sqlite3.Error:
        pass
    return conn


def run_migrations(conn: sqlite3.Connection) -> None:
    """Create tables and indexes if they do not exist."""
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            applied_at TEXT NOT NULL
        )
    """)

    # Runs: one row per analysis run
    cur.execute("""
        CREATE TABLE IF NOT EXISTS runs (
            run_id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            genre TEXT,
            document_title TEXT,
            document_author TEXT,
            metadata_json TEXT
        )
    """)

    # Chunk artifacts per run (context, analysis, detectors, etc. stored as JSON)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS run_chunks (
            run_id TEXT NOT NULL,
            chunk_id TEXT NOT NULL,
            position INTEGER NOT NULL,
            payload_json TEXT NOT NULL,
            PRIMARY KEY (run_id, chunk_id),
            FOREIGN KEY (run_id) REFERENCES runs(run_id)
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_run_chunks_run_id ON run_chunks(run_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_run_chunks_chunk_id ON run_chunks(chunk_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_run_chunks_run_position ON run_chunks(run_id, position)")

    # Document-level state per run (compressed)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS run_document_state (
            run_id TEXT PRIMARY KEY,
            payload_json TEXT NOT NULL,
            FOREIGN KEY (run_id) REFERENCES runs(run_id)
        )
    """)

    # Judgment versions: immutable audit trail
    cur.execute("""
        CREATE TABLE IF NOT EXISTS judgment_versions (
            run_id TEXT NOT NULL,
            chunk_id TEXT NOT NULL,
            version INTEGER NOT NULL,
            judgment_json TEXT NOT NULL,
            source TEXT NOT NULL,
            rationale TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            PRIMARY KEY (run_id, chunk_id, version),
            FOREIGN KEY (run_id) REFERENCES runs(run_id)
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_judgment_run_chunk ON judgment_versions(run_id, chunk_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_judgment_run_chunk_version ON judgment_versions(run_id, chunk_id, version)")

    # Chat turns (UX continuity only)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS chat_turns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            chunk_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            judgment_version INTEGER,
            created_at TEXT NOT NULL
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_chat_turns_run_chunk ON chat_turns(run_id, chunk_id)")

    # --- Extended lineage: link legacy runs to documents/revisions (nullable) ---
    add_column_if_missing(conn, "runs", "document_id", "TEXT")
    add_column_if_missing(conn, "runs", "revision_id", "TEXT")
    add_column_if_missing(conn, "runs", "analysis_kind", "TEXT DEFAULT 'full'")
    add_column_if_missing(conn, "chat_turns", "revision_id", "TEXT")
    add_column_if_missing(conn, "chat_turns", "chunk_version_id", "INTEGER")

    # Documents and SCD2 revisions
    cur.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            document_id TEXT PRIMARY KEY,
            title TEXT,
            author TEXT,
            writer_id TEXT,
            created_at TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}'
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS document_revisions (
            revision_id TEXT PRIMARY KEY,
            document_id TEXT NOT NULL,
            parent_revision_id TEXT,
            root_revision_id TEXT,
            branch_name TEXT,
            text_hash TEXT NOT NULL,
            full_text TEXT,
            byte_length INTEGER NOT NULL DEFAULT 0,
            diff_summary_json TEXT,
            valid_from TEXT NOT NULL,
            valid_to TEXT,
            is_current INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            FOREIGN KEY (document_id) REFERENCES documents(document_id)
        )
    """)
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_doc_rev_document ON document_revisions(document_id)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_doc_rev_current ON document_revisions(document_id, is_current)"
    )

    cur.execute("""
        CREATE TABLE IF NOT EXISTS chunk_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            revision_id TEXT NOT NULL,
            chunk_business_id TEXT NOT NULL,
            position INTEGER NOT NULL,
            start_char INTEGER NOT NULL,
            end_char INTEGER NOT NULL,
            valid_from TEXT NOT NULL,
            valid_to TEXT,
            is_current INTEGER NOT NULL DEFAULT 1,
            FOREIGN KEY (revision_id) REFERENCES document_revisions(revision_id)
        )
    """)
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_chunk_ver_rev ON chunk_versions(revision_id)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_chunk_ver_pos ON chunk_versions(revision_id, position)"
    )

    cur.execute("""
        CREATE TABLE IF NOT EXISTS dim_chapter (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            revision_id TEXT NOT NULL,
            ordinal INTEGER NOT NULL,
            label TEXT,
            start_char INTEGER NOT NULL,
            end_char INTEGER NOT NULL,
            FOREIGN KEY (revision_id) REFERENCES document_revisions(revision_id)
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_dim_chapter_rev ON dim_chapter(revision_id)")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS dim_section (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            revision_id TEXT NOT NULL,
            chapter_id INTEGER,
            beat_label TEXT,
            start_char INTEGER NOT NULL,
            end_char INTEGER NOT NULL,
            FOREIGN KEY (revision_id) REFERENCES document_revisions(revision_id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS dim_character (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id TEXT NOT NULL,
            canonical_name TEXT NOT NULL,
            role TEXT,
            notes TEXT,
            valid_from TEXT NOT NULL,
            valid_to TEXT,
            is_current INTEGER NOT NULL DEFAULT 1,
            FOREIGN KEY (document_id) REFERENCES documents(document_id)
        )
    """)
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_dim_char_doc ON dim_character(document_id, is_current)"
    )

    cur.execute("""
        CREATE TABLE IF NOT EXISTS dim_motif (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id TEXT NOT NULL,
            theme_key TEXT NOT NULL,
            label TEXT NOT NULL,
            FOREIGN KEY (document_id) REFERENCES documents(document_id)
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_dim_motif_doc ON dim_motif(document_id)")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS bridge_chunk_character (
            chunk_version_id INTEGER NOT NULL,
            character_id INTEGER NOT NULL,
            role_in_scene TEXT,
            confidence REAL,
            PRIMARY KEY (chunk_version_id, character_id),
            FOREIGN KEY (chunk_version_id) REFERENCES chunk_versions(id),
            FOREIGN KEY (character_id) REFERENCES dim_character(id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS bridge_chunk_motif (
            chunk_version_id INTEGER NOT NULL,
            motif_id INTEGER NOT NULL,
            weight REAL,
            PRIMARY KEY (chunk_version_id, motif_id),
            FOREIGN KEY (chunk_version_id) REFERENCES chunk_versions(id),
            FOREIGN KEY (motif_id) REFERENCES dim_motif(id)
        )
    """)

    # Star-schema style analytic facts (one row per measure / stage)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS analytic_facts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            analysis_run_id TEXT NOT NULL,
            revision_id TEXT NOT NULL,
            chunk_version_id INTEGER,
            fact_kind TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (revision_id) REFERENCES document_revisions(revision_id)
        )
    """)
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_analytic_run ON analytic_facts(analysis_run_id)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_analytic_rev_chunk ON analytic_facts(revision_id, chunk_version_id)"
    )

    cur.execute("""
        CREATE TABLE IF NOT EXISTS revision_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id TEXT NOT NULL,
            from_revision_id TEXT,
            to_revision_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            actor_id TEXT,
            reason TEXT,
            metadata_json TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (document_id) REFERENCES documents(document_id)
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_rev_events_doc ON revision_events(document_id)")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS restore_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            revision_event_id INTEGER NOT NULL,
            status TEXT NOT NULL,
            analysis_run_id TEXT,
            error TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (revision_event_id) REFERENCES revision_events(id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS user_bookmarks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id TEXT NOT NULL,
            label TEXT NOT NULL,
            revision_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (document_id) REFERENCES documents(document_id),
            FOREIGN KEY (revision_id) REFERENCES document_revisions(revision_id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS async_jobs (
            job_id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            status TEXT NOT NULL,
            document_id TEXT,
            revision_id TEXT,
            run_id TEXT,
            payload_json TEXT,
            result_json TEXT,
            error TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_async_jobs_status ON async_jobs(status)")

    conn.commit()


def init_db(db_path: str) -> sqlite3.Connection:
    """Create connection and run migrations. Call once at app startup."""
    conn = get_connection(db_path)
    run_migrations(conn)
    return conn
