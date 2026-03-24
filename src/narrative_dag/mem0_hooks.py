"""Optional Mem0 sync after analysis (summaries only; no raw manuscript by default)."""

from __future__ import annotations

import os
from typing import Any


def sync_document_summary_if_enabled(
    *,
    user_id: str,
    document_id: str,
    revision_id: str,
    document_summary: str,
    genre: str,
) -> None:
    """Push a compact summary to Mem0 when MEM0_API_KEY is set and package is installed."""
    if not os.getenv("MEM0_API_KEY", "").strip():
        return
    try:
        from mem0 import Memory  # type: ignore[import-untyped]
    except ImportError:
        try:
            from mem0ai import Memory  # type: ignore[import-untyped]
        except ImportError:
            return
    try:
        mem = Memory()
        text = (
            f"Genre: {genre}. Document {document_id} revision {revision_id}. "
            f"Summary: {document_summary[:4000]}"
        )
        mem.add(
            text,
            user_id=user_id,
            metadata={
                "document_id": document_id,
                "revision_id": revision_id,
                "kind": "analysis_summary",
            },
        )
    except Exception:
        return
