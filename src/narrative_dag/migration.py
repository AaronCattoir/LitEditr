"""Safe SQLite column additions and schema versioning helpers."""

from __future__ import annotations

import sqlite3


def table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    cur = conn.execute(f"PRAGMA table_info({table})")
    return {row[1] for row in cur.fetchall()}


def add_column_if_missing(
    conn: sqlite3.Connection, table: str, column: str, decl: str
) -> None:
    if column in table_columns(conn, table):
        return
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
