"""Tests for Pydantic schemas."""

from __future__ import annotations

import pytest
from narrative_dag.schemas import (
    Chunk,
    ContextWindow,
    EditorJudgment,
    GenreIntention,
    RawDocument,
)


def test_chunk_deterministic_id():
    c = Chunk(id="c1", text="Hello.", position=0, start_char=0, end_char=len("Hello."))
    assert c.id == "c1"
    assert c.position == 0


def test_genre_intention():
    g = GenreIntention(genre="thriller", subgenre_tags=["noir"])
    assert g.genre == "thriller"
    assert "noir" in g.subgenre_tags


def test_editor_judgment_keep():
    j = EditorJudgment(decision="keep", severity=0.2, reasoning="Fine.", core_issue="", guidance="", is_drift=False)
    assert j.decision == "keep"


def test_context_window():
    target = Chunk(id="c2", text="Mid.", position=1, start_char=0, end_char=len("Mid."))
    prev = Chunk(id="c1", text="First.", position=0, start_char=0, end_char=len("First."))
    ctx = ContextWindow(target_chunk=target, previous_chunks=[prev], next_chunks=[], global_summary="")
    assert ctx.target_chunk.id == "c2"
    assert len(ctx.previous_chunks) == 1
