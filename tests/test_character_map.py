"""Tests for global character map builder."""

from __future__ import annotations

from narrative_dag.nodes.character_map import character_map_builder
from narrative_dag.schemas import GenreIntention, PlotOverview, RawDocument


def test_character_map_builder_returns_database():
    state = {
        "raw_document": RawDocument(text="Lanky climbed the tower while Wayne watched from below."),
        "genre_intention": GenreIntention(genre="southern_gothic_horror"),
        "plot_overview": PlotOverview(
            plot_summary="A lineman spirals after hearing a dead line breathe.",
            story_point="Grief masks itself as haunting.",
        ),
    }
    out = character_map_builder(state)
    assert "character_database" in out
    db = out["character_database"]
    assert db.characters
    names = [c.canonical_name for c in db.characters]
    assert "Lanky" in names


def test_character_map_builder_empty_text_returns_empty_database():
    out = character_map_builder(
        {
            "raw_document": RawDocument(text="   \n "),
            "genre_intention": GenreIntention(genre="literary_fiction"),
        }
    )
    assert out["character_database"].characters == []
