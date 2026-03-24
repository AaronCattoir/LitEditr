"""Ingestion layer: LLM character chunker and context_builder."""

from __future__ import annotations

import re
from typing import Any

from narrative_dag.config import DEFAULT_CONTEXT_WINDOW_SIZE, CHUNKER_MAX_ONE_SHOT_CHARS, CHAPTER_DETECTION_MAX_CHARS
import narrative_dag.llm as llm_runtime
from narrative_dag.llm import structured_invoke
from narrative_dag.prompts.ingestion import chunk_boundary_prompt
from narrative_dag.schemas import Chunk, ChunkBoundaries, ContextWindow
from langchain_core.messages import HumanMessage


SECTION_DELIMITER_RE = re.compile(r"(?m)^[ \t]*~+[ \t]*$")


def _chunk_by_section_delimiter(text: str) -> list[Chunk]:
    """Deterministically split document on line-only '~' delimiters.

    Each delimiter line marks the start of a new section. This path avoids
    LLM chunking entirely when users provide explicit section separators.
    """
    n = len(text)
    if n == 0:
        return []

    cut_points = [0] + [m.start() for m in SECTION_DELIMITER_RE.finditer(text)] + [n]
    cut_points = sorted(set(c for c in cut_points if 0 <= c <= n))
    # No delimiter discovered -> caller can continue with other strategies.
    if len(cut_points) <= 2:
        return []

    chunks: list[Chunk] = []
    for s, e in zip(cut_points, cut_points[1:]):
        if e <= s:
            continue
        segment = text[s:e]
        if not segment.strip():
            continue
        chunks.append(
            Chunk(
                id=f"c{len(chunks) + 1}",
                text=segment,
                position=len(chunks),
                start_char=s,
                end_char=e,
            )
        )
    return chunks


def chunk_document(text: str) -> list[Chunk]:
    """Deterministic paragraph chunking with character offsets (fallback/utility)."""
    section_chunks = _chunk_by_section_delimiter(text)
    if section_chunks:
        return section_chunks

    # Separator: blank line region (two+ line breaks with optional whitespace between).
    sep_re = re.compile(r"(?:\r?\n)\s*(?:\r?\n)+")
    chunks: list[Chunk] = []
    last = 0
    idx = 0
    for m in sep_re.finditer(text):
        block = text[last : m.start()]
        block_stripped = block.strip()
        if block_stripped:
            # Compute stripped offsets within the original text block.
            ltrim = len(block) - len(block.lstrip())
            rtrim = len(block) - len(block.rstrip())
            start_char = last + ltrim
            end_char = m.start() - rtrim
            if end_char > start_char:
                chunks.append(
                    Chunk(
                        id=f"c{idx + 1}",
                        text=text[start_char:end_char],
                        position=idx,
                        start_char=start_char,
                        end_char=end_char,
                    )
                )
                idx += 1
        last = m.end()
    # Tail block
    block = text[last:]
    block_stripped = block.strip()
    if block_stripped:
        ltrim = len(block) - len(block.lstrip())
        rtrim = len(block) - len(block.rstrip())
        start_char = last + ltrim
        end_char = len(text) - rtrim
        if end_char > start_char:
            chunks.append(
                Chunk(
                    id=f"c{idx + 1}",
                    text=text[start_char:end_char],
                    position=idx,
                    start_char=start_char,
                    end_char=end_char,
                )
            )
    return chunks


def _normalize_char_chunks(text: str, boundaries: ChunkBoundaries) -> list[tuple[int, int]]:
    """Turn LLM boundaries into a contiguous, non-overlapping partition using start_char cuts."""
    n = len(text)
    if not boundaries or not boundaries.boundaries:
        return [(0, n)] if n > 0 else []

    proposed_starts = []
    for b in boundaries.boundaries:
        s = int(b.start_char)
        s = max(0, min(s, n))
        proposed_starts.append(s)

    # Use unique starts as cut points; end is implied by the next cut, last cut ends at len(text).
    cuts = sorted(set(proposed_starts))
    if 0 not in cuts:
        cuts = [0] + cuts
    if n not in cuts:
        cuts.append(n)
    # Ensure monotonic segments.
    segments: list[tuple[int, int]] = []
    for i in range(len(cuts) - 1):
        start = cuts[i]
        end = cuts[i + 1]
        if end > start:
            segments.append((start, end))
    if not segments and n > 0:
        segments = [(0, n)]
    return segments


def narrative_chunk_document(text: str, genre: str, llm: Any) -> list[Chunk]:
    """Split document into narrative beats using LLM-defined character boundaries."""
    if not text.strip():
        return []

    prompt = chunk_boundary_prompt(text, genre=genre)
    boundaries = structured_invoke(llm, [HumanMessage(content=prompt)], ChunkBoundaries)
    segments = _normalize_char_chunks(text, boundaries)

    chunks: list[Chunk] = []
    for idx, (start_char, end_char) in enumerate(segments):
        chunk_text = text[start_char:end_char]
        if not chunk_text:
            continue
        chunks.append(
            Chunk(
                id=f"c{idx + 1}",
                text=chunk_text,
                position=idx,
                start_char=start_char,
                end_char=end_char,
            )
        )
    return chunks


def _detect_chapter_spans(text: str, chapter_markers: list[str] | None) -> list[tuple[int, int]]:
    """Detect chapter spans in a document; returns contiguous spans covering [0, len(text)]."""
    n = len(text)
    if n == 0:
        return []

    if chapter_markers:
        # If user supplies markers, use them as anchors.
        # Each marker is treated as a literal substring that begins a chapter.
        starts = []
        for marker in chapter_markers:
            for m in re.finditer(re.escape(marker), text, flags=re.IGNORECASE):
                starts.append(m.start())
        starts = sorted(set(starts))
    else:
        # Heuristic headings: "Chapter", "CHAPTER", "Part", "PART" at line start.
        rx = re.compile(r"(?m)^(chapter\b|part\b)\s+[^\n]+", flags=re.IGNORECASE)
        starts = [m.start() for m in rx.finditer(text)]

    # Always cover the whole doc.
    if not starts:
        return [(0, n)]
    # Filter out near-duplicates and ensure first/last.
    starts = [s for s in starts if 0 <= s < n]
    starts = sorted(set(starts))
    if starts and starts[0] != 0:
        starts = [0] + starts
    # Build spans from each start to next start.
    spans: list[tuple[int, int]] = []
    for i, s in enumerate(starts):
        e = starts[i + 1] if i + 1 < len(starts) else n
        if e > s:
            spans.append((s, e))
    return spans


def chapter_then_chunk_document(text: str, genre: str, llm: Any, chapter_markers: list[str] | None) -> list[Chunk]:
    """For long docs: detect chapters, one-shot chunk each, stitch global char offsets."""
    if not text.strip():
        return []

    spans = _detect_chapter_spans(text, chapter_markers)
    all_chunks: list[Chunk] = []

    for span_start, span_end in spans:
        chapter_text = text[span_start:span_end]
        if not chapter_text.strip():
            continue

        # If a single chapter is still too large, we fall back to paragraph chunking for safety.
        if len(chapter_text) > CHAPTER_DETECTION_MAX_CHARS:
            for c in chunk_document(chapter_text):
                all_chunks.append(
                    Chunk(
                        id=f"c{len(all_chunks) + 1}",
                        text=c.text,
                        position=len(all_chunks),
                        start_char=span_start + c.start_char,
                        end_char=span_start + c.end_char,
                    )
                )
            continue

        local_chunks = narrative_chunk_document(chapter_text, genre, llm)
        for lc in local_chunks:
            all_chunks.append(
                Chunk(
                    id=f"c{len(all_chunks) + 1}",
                    text=lc.text,
                    position=len(all_chunks),
                    start_char=span_start + lc.start_char,
                    end_char=span_start + lc.end_char,
                )
            )
    # Final normalization: rebuild a single contiguous partition for the whole document.
    # This absorbs any gaps introduced by deterministic fallback chunking.
    n = len(text)
    cut_points = sorted(set([0] + [c.start_char for c in all_chunks] + [n]))
    rebuilt: list[Chunk] = []
    for i in range(len(cut_points) - 1):
        s = cut_points[i]
        e = cut_points[i + 1]
        if e <= s:
            continue
        rebuilt.append(
            Chunk(
                id=f"c{i + 1}",
                text=text[s:e],
                position=len(rebuilt),
                start_char=s,
                end_char=e,
            )
        )
    return rebuilt


def build_context_window(
    chunks: list[Chunk],
    chunk_id: str,
    window_size: int = DEFAULT_CONTEXT_WINDOW_SIZE,
    global_summary: str = "",
) -> ContextWindow:
    """Build local + global context for a target chunk. Sliding window of previous/next chunks."""
    target_idx = next((i for i, c in enumerate(chunks) if c.id == chunk_id), None)
    if target_idx is None:
        raise ValueError(f"chunk_id {chunk_id} not found")
    target = chunks[target_idx]
    start = max(0, target_idx - window_size)
    end = min(len(chunks), target_idx + window_size + 1)
    previous = chunks[start:target_idx]
    next_chunks = chunks[target_idx + 1 : end]
    return ContextWindow(
        target_chunk=target,
        previous_chunks=previous,
        next_chunks=next_chunks,
        global_summary=global_summary,
    )


def run_chunker(state: dict[str, Any]) -> dict[str, Any]:
    """LangGraph node: run LLM narrative chunker on raw document."""
    raw = state.get("raw_document")
    if not raw:
        text = state.get("document_text", "")
        from narrative_dag.schemas import RawDocument
        raw = RawDocument(text=text)
    if hasattr(raw, "text"):
        text = raw.text
    else:
        text = str(raw.get("text", ""))
    genre = state.get("genre_intention")
    genre_value = getattr(genre, "genre", "literary_fiction") if genre else "literary_fiction"
    chapter_markers = getattr(raw, "chapter_markers", None) if hasattr(raw, "chapter_markers") else None

    # Explicit user section delimiters ('~' on their own line) should always win.
    # This keeps chunking deterministic and avoids slow LLM chunk detection.
    explicit_section_chunks = _chunk_by_section_delimiter(text)
    if explicit_section_chunks:
        chunks = explicit_section_chunks
        return {"chunks": chunks}

    llm = state.get("_llm") or llm_runtime.get_llm()
    if len(text) <= CHUNKER_MAX_ONE_SHOT_CHARS:
        chunks = narrative_chunk_document(text, genre_value, llm)
    else:
        # Novel-size strategy: chapter-first.
        chunks = chapter_then_chunk_document(text, genre_value, llm, chapter_markers)
    return {"chunks": chunks}


def run_context_builder(state: dict[str, Any]) -> dict[str, Any]:
    """LangGraph node: for current_chunk_id, build context window. Expects chunks + optional global_summary."""
    chunks = state.get("chunks", [])
    chunk_id = state.get("current_chunk_id")
    global_summary = state.get("global_summary", "")
    if not chunks or not chunk_id:
        return {}
    ctx = build_context_window(chunks, chunk_id, global_summary=global_summary)
    return {"context_window": ctx}
