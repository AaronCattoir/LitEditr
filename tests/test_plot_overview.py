"""Unit tests for plot_overview_builder node."""

from __future__ import annotations

import pytest
from narrative_dag.schemas import GenreIntention, RawDocument
from narrative_dag.nodes.plot_overview import plot_overview_builder


def test_plot_overview_builder_returns_overview_and_global_summary():
    """plot_overview_builder returns plot_overview and global_summary from raw_document."""
    state = {
        "raw_document": RawDocument(text="Opening line. Then more text here for the story.\n\nSecond paragraph."),
        "chunks": [],
        "genre_intention": GenreIntention(genre="literary_fiction"),
    }
    out = plot_overview_builder(state)
    assert "plot_overview" in out
    assert "global_summary" in out
    assert out["plot_overview"] is not None
    assert out["plot_overview"].plot_summary
    assert out["plot_overview"].story_point
    assert out["global_summary"] == out["plot_overview"].plot_summary


def test_plot_overview_builder_from_chunks_when_no_raw_document():
    """When raw_document is missing, build from concatenated chunks."""
    from narrative_dag.schemas import Chunk
    state = {
        "chunks": [
            Chunk(id="c1", text="First part.", position=0, start_char=0, end_char=len("First part.")),
            Chunk(id="c2", text="Second part.", position=1, start_char=0, end_char=len("Second part.")),
        ],
        "genre_intention": GenreIntention(genre="thriller"),
    }
    out = plot_overview_builder(state)
    assert out["plot_overview"] is not None
    assert out["plot_overview"].plot_summary
    assert isinstance(out["plot_overview"].arc_map, list)
    assert isinstance(out["plot_overview"].stakes, str)


def test_plot_overview_builder_empty_text_returns_none_overview():
    """Empty document yields None plot_overview and empty global_summary."""
    state = {
        "raw_document": RawDocument(text="   \n\n  "),
        "chunks": [],
        "genre_intention": GenreIntention(genre="literary_fiction"),
    }
    out = plot_overview_builder(state)
    assert out["plot_overview"] is None
    assert out["global_summary"] == ""


def test_plot_overview_persisted_in_document_state_after_analyze(temp_db_path):
    """Run analyze via service; load document_state from RunStore; plot_overview is present."""
    from narrative_dag.service import NarrativeAnalysisService
    from narrative_dag.contracts import AnalyzeDocumentRequest
    from narrative_dag.db import init_db
    from narrative_dag.store.run_store import RunStore

    service = NarrativeAnalysisService(db_path=temp_db_path)
    request = AnalyzeDocumentRequest(
        document_text="Start of story.\n\nMiddle bit.\n\nEnd.",
        genre="literary_fiction",
    )
    response = service.analyze_document(request)
    service.close()
    assert response.success and response.run_id

    conn = init_db(temp_db_path)
    store = RunStore(conn)
    doc_state = store.get_document_state(response.run_id)
    conn.close()
    assert doc_state is not None
    assert doc_state.plot_overview is not None
    assert doc_state.plot_overview.story_point
    assert doc_state.plot_overview.plot_summary
