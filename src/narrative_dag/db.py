"""SQLite engine/session setup and migration bootstrap."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


def get_connection(db_path: str) -> sqlite3.Connection:
    """Return a connection to the SQLite database; creates file if needed."""
    if db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def run_migrations(conn: sqlite3.Connection) -> None:
    """Create tables and indexes if they do not exist."""
    cur = conn.cursor()

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

    conn.commit()


def init_db(db_path: str) -> sqlite3.Connection:
    """Create connection and run migrations. Call once at app startup."""
    conn = get_connection(db_path)
    run_migrations(conn)
    return conn
