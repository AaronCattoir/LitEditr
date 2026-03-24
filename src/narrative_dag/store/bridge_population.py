"""Populate bridge_chunk_character / dim_character from chunk text and character database."""

from __future__ import annotations

from typing import Any

from narrative_dag.schemas import CharacterDatabase, CharacterEntry, Chunk


def ensure_characters(
    conn: Any,
    document_id: str,
    character_database: CharacterDatabase | dict | None,
) -> dict[str, int]:
    """Insert dim_character rows; return map canonical_name -> id."""
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()
    if character_database is None:
        return {}
    if isinstance(character_database, dict):
        character_database = CharacterDatabase.model_validate(character_database)
    name_to_id: dict[str, int] = {}
    cur = conn.cursor()
    for ch in character_database.characters:
        entry: CharacterEntry = ch if isinstance(ch, CharacterEntry) else CharacterEntry.model_validate(ch)
        name = (entry.canonical_name or "").strip()
        if not name:
            continue
        cur.execute(
            """
            SELECT id FROM dim_character
            WHERE document_id = ? AND canonical_name = ? AND is_current = 1
            """,
            (document_id, name),
        )
        row = cur.fetchone()
        if row:
            name_to_id[name] = row[0]
            continue
        cur.execute(
            """
            INSERT INTO dim_character (document_id, canonical_name, role, notes, valid_from, valid_to, is_current)
            VALUES (?, ?, ?, ?, ?, NULL, 1)
            """,
            (document_id, name, entry.role or "", entry.notes or "", now),
        )
        name_to_id[name] = int(cur.lastrowid)
    conn.commit()
    return name_to_id


def populate_chunk_character_bridges(
    conn: Any,
    chunk_version_id: int,
    chunk: Chunk,
    character_database: CharacterDatabase | dict | None,
    name_to_id: dict[str, int],
) -> None:
    """Heuristic: link characters whose name or alias appears in chunk text."""
    if character_database is None:
        return
    if isinstance(character_database, dict):
        character_database = CharacterDatabase.model_validate(character_database)
    text_lower = chunk.text.lower()
    cur = conn.cursor()
    for ch in character_database.characters:
        entry = ch if isinstance(ch, CharacterEntry) else CharacterEntry.model_validate(ch)
        names = [entry.canonical_name] + list(entry.aliases or [])
        for n in names:
            n = (n or "").strip()
            if len(n) < 2:
                continue
            if n.lower() in text_lower:
                cid = name_to_id.get(entry.canonical_name or "")
                if cid:
                    cur.execute(
                        """
                        INSERT OR REPLACE INTO bridge_chunk_character (chunk_version_id, character_id, role_in_scene, confidence)
                        VALUES (?, ?, ?, ?)
                        """,
                        (chunk_version_id, cid, entry.role or "", 0.6),
                    )
                break
    conn.commit()
