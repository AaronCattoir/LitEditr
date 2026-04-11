"""Load markdown pet soul seed (global + per-story override)."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any


def _repo_root() -> Path:
    # narrative_dag/pet_soul.py -> parents[2] = project root (contains docs/)
    return Path(__file__).resolve().parents[2]


def pet_soul_paths(document_id: str | None = None) -> tuple[Path | None, Path | None]:
    """Return (global_soul_path, story_override_path). Either may be missing."""
    override_base = os.getenv("EDITR_PET_SOUL_DIR", "").strip()
    if override_base:
        root = Path(override_base)
    else:
        root = _repo_root() / "docs" / "pet"
    global_path = root / "PET_SOUL.md"
    story_path = None
    if document_id:
        story_path = root / "stories" / f"{document_id}.md"
    return (global_path if global_path.is_file() else None, story_path if story_path and story_path.is_file() else None)


def load_pet_soul_markdown(document_id: str | None = None) -> dict[str, Any]:
    """Return raw markdown and metadata for soul seed used at instantiation."""
    g, s = pet_soul_paths(document_id)
    parts: list[str] = []
    paths_used: list[str] = []
    if g:
        parts.append(g.read_text(encoding="utf-8"))
        paths_used.append(str(g))
    if s:
        parts.append(s.read_text(encoding="utf-8"))
        paths_used.append(str(s))
    combined = "\n\n---\n\n".join(parts) if parts else ""
    h = hashlib.sha256(combined.encode("utf-8")).hexdigest()[:16] if combined else ""
    return {
        "markdown": combined,
        "paths": paths_used,
        "hash": h,
        "primary_path": str(s) if s else (str(g) if g else ""),
    }


def parse_soul_sections(markdown: str) -> dict[str, str]:
    """Split markdown into sections by ## Heading."""
    sections: dict[str, str] = {}
    if not markdown.strip():
        return sections
    current_title = "Preamble"
    buf: list[str] = []
    for line in markdown.splitlines():
        if line.startswith("## "):
            if buf:
                sections[current_title] = "\n".join(buf).strip()
            current_title = line[3:].strip()
            buf = []
        else:
            buf.append(line)
    if buf:
        sections[current_title] = "\n".join(buf).strip()
    return sections
