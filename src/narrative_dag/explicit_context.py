"""Explicit context pack for story chat (no RAG): chunks or chapter slice."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import narrative_dag.config as config_module
from narrative_dag.persona.engine import count_words
from narrative_dag.store.document_store import DocumentStore

_DEBUG_LOG = Path(__file__).resolve().parents[2] / "debug-f3ece6.log"


def _agent_dbg(hypothesis_id: str, message: str, data: dict[str, Any]) -> None:
    # region agent log
    try:
        payload = {
            "sessionId": "f3ece6",
            "hypothesisId": hypothesis_id,
            "location": "explicit_context.build_explicit_context",
            "message": message,
            "data": data,
            "timestamp": int(time.time() * 1000),
        }
        with _DEBUG_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, default=str) + "\n")
    except OSError:
        pass
    # endregion agent log


def _words_prefix(text: str, max_words: int) -> tuple[str, bool]:
    words = (text or "").split()
    if len(words) <= max_words:
        return (" ".join(words), False)
    return (" ".join(words[:max_words]), True)


def build_explicit_context(
    ds: DocumentStore,
    *,
    revision_id: str,
    chunk_ids: list[str] | None,
    chapter_id: str | None,
    max_words: int | None = None,
) -> tuple[dict[str, Any], str, str | None]:
    """
    Returns (manifest, combined_text, error_code).
    error_code: None | chunk_not_found | revision_not_found | no_manuscript
    """
    mw = max_words if max_words is not None else config_module.STORY_CHAT_MAX_WORDS_DEFAULT
    rev = ds.get_revision(revision_id)
    if not rev:
        return (
            {"revision_id": revision_id, "scope": "error"},
            "",
            "revision_not_found",
        )
    full = rev.get("full_text") or ""
    if not full.strip():
        return (
            {"revision_id": revision_id, "scope": "error"},
            "",
            "no_manuscript",
        )
    document_id = str(rev["document_id"])

    if chunk_ids:
        texts: list[str] = []
        missing: list[str] = []
        cv_map = ds.get_chunk_version_map(revision_id)
        order = {cid: pos for cid, pos in ds.list_chunk_business_ids_ordered(revision_id)}
        for cid in sorted(chunk_ids, key=lambda c: order.get(c, 10**9)):
            t = ds.get_revision_chunk_text(revision_id, cid)
            if t is None:
                missing.append(cid)
            else:
                texts.append(t)
        if missing:
            _agent_dbg(
                "D_E",
                "chunk_ids missing on revision",
                {
                    "revision_id": revision_id,
                    "document_id": document_id,
                    "requested": list(chunk_ids),
                    "missing": missing,
                    "n_chunk_versions": len(cv_map),
                    "cv_keys_sample": sorted(cv_map.keys())[:12],
                    "requested_in_cv_map": [c for c in chunk_ids if c in cv_map],
                },
            )
            return (
                {
                    "revision_id": revision_id,
                    "document_id": document_id,
                    "scope": "chunks",
                    "chunk_ids_requested": chunk_ids,
                    "missing_chunk_ids": missing,
                    "chunk_version_ids": {k: cv_map.get(k) for k in chunk_ids if k not in missing},
                },
                "",
                "chunk_not_found",
            )
        combined = "\n\n".join(texts)
        combined, truncated = _words_prefix(combined, mw)
        manifest = {
            "revision_id": revision_id,
            "document_id": document_id,
            "scope": "chunks",
            "chunk_ids": chunk_ids,
            "word_limit": mw,
            "truncated": truncated,
            "approx_word_count": count_words(combined),
        }
        return (manifest, combined, None)

    chapters = ds.list_document_chapters(document_id)
    if not chapters:
        combined, truncated = _words_prefix(full, mw)
        return (
            {
                "revision_id": revision_id,
                "document_id": document_id,
                "scope": "manuscript_prefix",
                "chapter_id": None,
                "note": "no document_chapters rows; using manuscript prefix",
                "word_limit": mw,
                "truncated": truncated,
            },
            combined,
            None,
        )

    sorted_ch = sorted(chapters, key=lambda c: (c["sort_order"], c.get("created_at") or ""))
    n = len(sorted_ch)
    if chapter_id:
        idx = next((i for i, c in enumerate(sorted_ch) if c["chapter_id"] == chapter_id), None)
        if idx is None:
            return (
                {
                    "revision_id": revision_id,
                    "document_id": document_id,
                    "scope": "chapter",
                    "chapter_id": chapter_id,
                    "error": "chapter_not_found",
                },
                "",
                "chapter_not_found",
            )
    else:
        idx = 0

    total_chars = len(full)
    if total_chars == 0:
        return ({"scope": "error"}, "", "no_manuscript")
    seg_len = max(1, total_chars // n)
    start = idx * seg_len
    end = total_chars if idx == n - 1 else min(total_chars, (idx + 1) * seg_len)
    segment = full[start:end]
    combined, truncated = _words_prefix(segment, mw)
    manifest = {
        "revision_id": revision_id,
        "document_id": document_id,
        "scope": "chapter_segment",
        "chapter_id": sorted_ch[idx]["chapter_id"] if sorted_ch else None,
        "chapter_title": sorted_ch[idx].get("title") if sorted_ch else "",
        "chapter_index": idx,
        "segment_char_start": start,
        "segment_char_end": end,
        "word_limit": mw,
        "truncated": truncated,
        "approx_word_count": count_words(combined),
    }
    return (manifest, combined, None)
