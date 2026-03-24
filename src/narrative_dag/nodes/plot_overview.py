"""Plot overview node: global story summary for editor context."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import HumanMessage

import narrative_dag.llm as llm_runtime
from narrative_dag.llm import structured_invoke
from narrative_dag.prompts.plot_overview import plot_overview_prompt
from narrative_dag.schemas import PlotOverview


def _full_text_from_state(state: dict[str, Any]) -> str:
    """Get full document text from raw_document or by concatenating chunks."""
    raw = state.get("raw_document")
    if raw:
        if hasattr(raw, "text"):
            return raw.text
        if isinstance(raw, dict):
            return raw.get("text", "")
    chunks = state.get("chunks") or []
    if chunks:
        return "\n\n".join(
            c.text if hasattr(c, "text") else c.get("text", "")
            for c in chunks
        )
    return ""


def plot_overview_builder(state: dict[str, Any]) -> dict[str, Any]:
    """Build an LLM-derived plot overview from document/chunks + genre."""
    text = _full_text_from_state(state)
    if not text.strip():
        return {"plot_overview": None, "global_summary": ""}
    llm = state.get("_llm") or llm_runtime.get_llm()
    genre = state.get("genre_intention")
    genre_value = getattr(genre, "genre", "literary_fiction") if genre else "literary_fiction"
    prompt = plot_overview_prompt(document_text=text, genre=genre_value)
    overview = structured_invoke(llm, [HumanMessage(content=prompt)], PlotOverview)
    return {
        "plot_overview": overview,
        "global_summary": overview.plot_summary,
    }
