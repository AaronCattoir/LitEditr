"""Sparkle quick-coach: single structured LLM call with slim narrative context."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import HumanMessage

import narrative_dag.llm as llm_runtime
from narrative_dag.llm import structured_invoke
from narrative_dag.prompt_context import PromptContext, build_prompt_context, format_prompt_context
from narrative_dag.prompts.quick_coach import quick_coach_prompt
from narrative_dag.schemas import ContextBundle, GenreIntention, QuickCoachAdvice


def _format_latest_critic_panel(bundle: ContextBundle) -> str:
    """Render current chunk's latest critic panel for quick-coach grounding."""
    critic = bundle.critic_result
    if critic is None:
        return ""
    lines = [
        "",
        "LATEST CRITIC PANEL (TARGET CHUNK)",
        f"Verdict: {critic.verdict}",
    ]
    critique = (critic.critique or "").strip()
    if critique:
        lines.append(f"Critique: {critique}")
    if critic.failure_points:
        lines.append("Failure points:")
        for p in critic.failure_points[:5]:
            t = (p or "").strip()
            if t:
                lines.append(f"- {t}")
    return "\n".join(lines)


def slim_narrative_text_from_bundle(
    bundle: ContextBundle, *, short_story_single_chapter: bool = False
) -> str:
    """Story + section context for quick coach, plus latest critic panel when available."""
    gi = bundle.genre_intention
    if gi is None and bundle.document_state and bundle.document_state.genre_intention:
        gi = bundle.document_state.genre_intention
    if short_story_single_chapter:
        if gi is not None:
            gi = gi.model_copy(update={"short_story_single_chapter": True})
        else:
            base_genre = "literary_fiction"
            if bundle.document_state and bundle.document_state.genre_intention:
                base_genre = bundle.document_state.genre_intention.genre or base_genre
            gi = GenreIntention(genre=base_genre, short_story_single_chapter=True)
    state: dict[str, Any] = {
        "context_window": bundle.context_window,
        "document_state": bundle.document_state,
        "plot_overview": bundle.document_state.plot_overview if bundle.document_state else None,
        "genre_intention": gi,
        "chunk_judgments": [],
    }
    pc = build_prompt_context(state)
    if pc is None:
        base = format_prompt_context(
            PromptContext(
                target_chunk=bundle.target_chunk,
                previous_chunks=bundle.context_window.previous_chunks,
                next_chunks=bundle.context_window.next_chunks,
                global_summary=bundle.context_window.global_summary,
                genre_intention=gi,
            )
        )
        return f"{base}{_format_latest_critic_panel(bundle)}"
    base = format_prompt_context(pc)
    return f"{base}{_format_latest_critic_panel(bundle)}"


def run_quick_coach(
    bundle: ContextBundle,
    focus: str | None,
    llm: Any | None = None,
    *,
    current_revision_text: str | None = None,
    short_story_single_chapter: bool = False,
) -> QuickCoachAdvice:
    """Return structured quick advice for a single chunk."""
    model = llm if llm is not None else llm_runtime.get_llm(stage="quick_coach")
    narrative = slim_narrative_text_from_bundle(
        bundle, short_story_single_chapter=short_story_single_chapter
    )
    prompt = quick_coach_prompt(
        narrative,
        focus or "",
        current_revision_text=current_revision_text,
    )
    return structured_invoke(model, [HumanMessage(content=prompt)], QuickCoachAdvice)
