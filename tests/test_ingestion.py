"""Tests for ingestion: chunker and context_builder."""

from __future__ import annotations

import pytest
from narrative_dag.nodes.ingestion import chunk_document, build_context_window
from narrative_dag.graph import run_analysis
from narrative_dag.schemas import GenreIntention, RawDocument
from narrative_dag.config import CHUNKER_MAX_ONE_SHOT_CHARS


def test_chunker_deterministic(sample_document):
    chunks = chunk_document(sample_document)
    assert len(chunks) == 4
    assert chunks[0].id == "c1"
    assert chunks[1].id == "c2"
    assert "First paragraph" in chunks[0].text
    assert sample_document[chunks[0].start_char : chunks[0].end_char] == chunks[0].text
    # Same input -> same IDs
    again = chunk_document(sample_document)
    assert [c.id for c in again] == [c.id for c in chunks]


def test_chunker_empty():
    assert chunk_document("") == []
    assert chunk_document("\n\n   \n\n") == []


def test_chunker_uses_tilde_section_delimiter():
    doc = "Section one starts here.\nStill section one.\n~\nSection two starts here.\n~\nSection three."
    chunks = chunk_document(doc)
    assert len(chunks) == 3
    assert chunks[0].id == "c1"
    assert chunks[1].id == "c2"
    assert chunks[2].id == "c3"
    assert "Section one starts here." in chunks[0].text
    assert "Section two starts here." in chunks[1].text
    assert "Section three." in chunks[2].text
    for c in chunks:
        assert doc[c.start_char : c.end_char] == c.text


def test_build_context_window(sample_document):
    chunks = chunk_document(sample_document)
    ctx = build_context_window(chunks, "c2", window_size=1)
    assert ctx.target_chunk.id == "c2"
    assert len(ctx.previous_chunks) == 1
    assert ctx.previous_chunks[0].id == "c1"
    assert len(ctx.next_chunks) == 1
    assert ctx.next_chunks[0].id == "c3"


def test_build_context_window_first_chunk(sample_document):
    chunks = chunk_document(sample_document)
    ctx = build_context_window(chunks, "c1", window_size=2)
    assert ctx.target_chunk.id == "c1"
    assert len(ctx.previous_chunks) == 0
    assert len(ctx.next_chunks) == 2


def test_long_doc_chapter_then_chunk_char_offsets():
    """Novel-sized input should use chapter-first chunking and produce valid contiguous char spans."""
    # Build a long enough doc to force the chapter-first path.
    target = CHUNKER_MAX_ONE_SHOT_CHARS + 500
    filler = "Filler sentence for chunking. "
    para = filler * (target // len(filler) // 2)
    chapter1 = "Chapter 1\n" + para + "\n\n" + para
    chapter2 = "Chapter 2\n" + para + "\n\n" + para
    doc = chapter1 + "\n\n" + chapter2
    assert len(doc) > CHUNKER_MAX_ONE_SHOT_CHARS

    genre = GenreIntention(genre="literary_fiction")
    state, _ = run_analysis(RawDocument(text=doc), genre, "long-doc-run")
    chunks = state["chunks"]
    assert chunks, "Expected at least one chunk"

    # Partition coverage + contiguity.
    assert chunks[0].start_char == 0
    assert chunks[-1].end_char == len(doc)
    for i in range(len(chunks) - 1):
        assert chunks[i].end_char == chunks[i + 1].start_char

    # Each chunk text must match the slice from the original doc.
    for c in chunks:
        assert doc[c.start_char : c.end_char] == c.text
