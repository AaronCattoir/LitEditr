"""Validate client-supplied chunk spans and build Chunk models (skip internal chunker)."""

from __future__ import annotations

from narrative_dag.schemas import Chunk


def validate_and_build_chunks_from_spans(
    doc_text: str,
    spans: list[tuple[str, int, int]],
) -> list[Chunk]:
    """
    spans: list of (chunk_id, start_char, end_char) end-exclusive, **Unicode code point** indices
    matching Python 3 str slicing (same as len(doc_text) positions). Must partition doc_text
    with no gaps or overlaps. (Not JavaScript String UTF-16 indices.)
    """
    if not spans:
        raise ValueError("chunks list must be non-empty when client chunking is used")
    n = len(doc_text)
    sorted_spans = sorted(spans, key=lambda s: (s[1], s[2]))
    seen_ids: set[str] = set()
    pos = 0
    chunks: list[Chunk] = []
    for i, (chunk_id, start, end) in enumerate(sorted_spans):
        if chunk_id in seen_ids:
            raise ValueError(f"duplicate chunk_id: {chunk_id!r}")
        seen_ids.add(chunk_id)
        if start != pos:
            raise ValueError(
                f"chunk spans must cover text contiguously: expected start {pos}, got {start}"
            )
        if end <= start:
            raise ValueError(f"end_char must be > start_char for chunk {chunk_id!r}")
        if end > n:
            raise ValueError("end_char exceeds document length")
        chunk_text = doc_text[start:end]
        chunks.append(
            Chunk(
                id=chunk_id,
                text=chunk_text,
                position=i,
                start_char=start,
                end_char=end,
            )
        )
        pos = end
    if pos != n:
        raise ValueError(
            f"chunk spans must cover full document: covered up to {pos}, length {n}"
        )
    return chunks
