"""Character map node: build canonical cast database from full document."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import HumanMessage

import narrative_dag.llm as llm_runtime
from narrative_dag.llm import structured_invoke
from narrative_dag.prompts.character_map import character_map_prompt
from narrative_dag.schemas import CharacterDatabase


def _full_text_from_state(state: dict[str, Any]) -> str:
    raw = state.get("raw_document")
    if raw:
        if hasattr(raw, "text"):
            return raw.text
        if isinstance(raw, dict):
            return raw.get("text", "")
    chunks = state.get("chunks") or []
    if chunks:
        return "\n\n".join(c.text if hasattr(c, "text") else c.get("text", "") for c in chunks)
    return ""


def character_map_builder(state: dict[str, Any]) -> dict[str, Any]:
    """Build document-level canonical character database."""
    text = _full_text_from_state(state)
    if not text.strip():
        return {"character_database": CharacterDatabase()}
    llm = state.get("_llm") or llm_runtime.get_llm()
    genre = state.get("genre_intention")
    genre_value = getattr(genre, "genre", "literary_fiction") if genre else "literary_fiction"
    plot = state.get("plot_overview")
    plot_summary = getattr(plot, "plot_summary", "") if plot is not None else ""
    story_point = getattr(plot, "story_point", "") if plot is not None else ""
    prompt = character_map_prompt(
        document_text=text,
        genre=genre_value,
        plot_summary=plot_summary,
        story_point=story_point,
    )
    character_db = structured_invoke(llm, [HumanMessage(content=prompt)], CharacterDatabase)
    return {"character_database": character_db}
