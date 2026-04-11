"""Helpers for assembling and formatting prompt-facing editorial context."""

from __future__ import annotations

from typing import Any

from narrative_dag.schemas import (
    ChunkJudgmentEntry,
    ContextWindow,
    DocumentState,
    GenreIntention,
    PlotOverview,
    PromptContext,
)


def build_prompt_context(state: dict[str, Any]) -> PromptContext | None:
    """Build a normalized context bundle from the current graph state."""
    ctx = state.get("context_window")
    if isinstance(ctx, dict):
        ctx = ContextWindow.model_validate(ctx)
    if not isinstance(ctx, ContextWindow):
        return None

    doc_state = state.get("document_state")
    if isinstance(doc_state, dict):
        doc_state = DocumentState.model_validate(doc_state)
    plot = state.get("plot_overview")
    if isinstance(plot, dict):
        plot = PlotOverview.model_validate(plot)
    if plot is None and isinstance(doc_state, DocumentState):
        plot = doc_state.plot_overview

    genre = state.get("genre_intention")
    if isinstance(genre, dict):
        genre = GenreIntention.model_validate(genre)
    if genre is None and isinstance(doc_state, DocumentState):
        genre = doc_state.genre_intention

    prior_entries: list[dict[str, Any]] = []
    for entry in state.get("chunk_judgments", [])[-3:]:
        if isinstance(entry, ChunkJudgmentEntry):
            prior_entries.append(entry.model_dump())
        elif isinstance(entry, dict):
            prior_entries.append(entry)

    return PromptContext(
        target_chunk=ctx.target_chunk,
        previous_chunks=ctx.previous_chunks,
        next_chunks=ctx.next_chunks,
        global_summary=ctx.global_summary,
        plot_summary=getattr(plot, "plot_summary", "") if plot else "",
        story_point=getattr(plot, "story_point", "") if plot else "",
        stakes=getattr(plot, "stakes", "") if plot else "",
        theme_hypotheses=list(getattr(plot, "theme_hypotheses", []) or []),
        emotional_curve=list(getattr(doc_state, "emotional_curve", []) or []),
        narrative_map=list(getattr(doc_state, "narrative_map", []) or []),
        character_voice_map=dict(getattr(doc_state, "character_voice_map", {}) or {}),
        character_database=[
            c.model_dump() if hasattr(c, "model_dump") else c
            for c in list(getattr(getattr(doc_state, "character_database", None), "characters", []) or [])
        ],
        prior_chunk_judgments=prior_entries,
        genre_intention=genre if isinstance(genre, GenreIntention) else None,
    )


def join_chunks(chunks: list[Any]) -> str:
    """Render neighboring chunks for prompt display."""
    if not chunks:
        return ""
    return "\n\n".join(getattr(c, "text", str(c)) for c in chunks)


def format_genre_context(genre: GenreIntention | None) -> str:
    """Render genre and taste metadata."""
    if not genre:
        return "Primary genre: literary_fiction"

    parts = [f"Primary genre: {genre.genre or 'literary_fiction'}"]
    if genre.subgenre_tags:
        parts.append("Subgenre tags: " + ", ".join(genre.subgenre_tags))
    if genre.tone_descriptors:
        parts.append("Tone descriptors: " + ", ".join(genre.tone_descriptors))
    if genre.reference_authors:
        parts.append("Reference authors: " + ", ".join(genre.reference_authors))
    if getattr(genre, "short_story_single_chapter", False):
        parts.append(
            "Work shape: SHORT STORY (single chapter / stand-alone). "
            "Do not penalize the text for lacking multi-chapter arc setup; "
            "judge completeness, payoff, and craft within this one piece."
        )
    return "\n".join(parts)


def format_prompt_context(ctx: PromptContext) -> str:
    """Render the structured prompt context as readable text."""
    lines = [
        "NARRATIVE CONTEXT",
        format_genre_context(ctx.genre_intention),
        f"Story point: {ctx.story_point}",
        f"Plot summary: {ctx.plot_summary or ctx.global_summary}",
        f"Stakes: {ctx.stakes}",
    ]
    if ctx.theme_hypotheses:
        lines.append("Theme hypotheses: " + ", ".join(ctx.theme_hypotheses))
    if ctx.emotional_curve:
        lines.append("Recent emotional trajectory: " + repr(ctx.emotional_curve[-5:]))
    if ctx.narrative_map:
        lines.append("Recent narrative trajectory: " + repr(ctx.narrative_map[-5:]))
    if ctx.character_voice_map:
        lines.append("Known character voice map: " + repr(ctx.character_voice_map))
    if ctx.character_database:
        lines.append("Canonical character map: " + repr(ctx.character_database))
    if ctx.prior_chunk_judgments:
        lines.append("Recent chunk judgments: " + repr(ctx.prior_chunk_judgments))
    lines.extend(
        [
            "",
            "PREVIOUS CONTEXT (reference only — do not critique)",
            join_chunks(ctx.previous_chunks) or "(none)",
            "",
            "TARGET CHUNK ← critique this chunk only",
            ctx.target_chunk.text,
            "",
            "NEXT CONTEXT (reference only — do not critique)",
            join_chunks(ctx.next_chunks) or "(none)",
        ]
    )
    return "\n".join(lines)
