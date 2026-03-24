"""Tests for interaction layer: explain and reconsider."""

from __future__ import annotations

import pytest
import narrative_dag.llm as llm_runtime
from narrative_dag.schemas import Chunk, ContextBundle, ContextWindow, EditorJudgment, GenreIntention
from narrative_dag.nodes.interaction import judge_explainer, judge_reconsideration


@pytest.fixture
def context_bundle():
    ch = Chunk(id="c1", text="Sample chunk.", position=0, start_char=0, end_char=len("Sample chunk."))
    ctx = ContextWindow(target_chunk=ch, previous_chunks=[], next_chunks=[], global_summary="")
    from narrative_dag.schemas import DocumentState
    return ContextBundle(
        target_chunk=ch,
        context_window=ctx,
        document_state=DocumentState(),
        current_judgment=EditorJudgment(decision="keep", reasoning="Looks good.", core_issue="", guidance=""),
        genre_intention=GenreIntention(genre="literary_fiction"),
    )


def test_judge_explainer(context_bundle):
    reply = judge_explainer(context_bundle, "Why keep?", llm_runtime.get_llm())
    assert reply


def test_judge_reconsideration(context_bundle):
    new_j = judge_reconsideration(context_bundle, "Reconsider because of tone.", llm_runtime.get_llm())
    assert new_j.decision in ("keep", "cut", "rewrite")
    assert new_j.reasoning
