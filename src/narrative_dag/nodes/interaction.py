"""Interaction layer: judge_chat_router, judge_explainer, judge_reconsideration (context-pinned)."""

from __future__ import annotations

from typing import Any, Literal

from langchain_core.messages import HumanMessage

import narrative_dag.llm as llm_runtime
from narrative_dag.llm import structured_invoke
from narrative_dag.prompt_context import PromptContext, format_prompt_context
from narrative_dag.prompts.interaction import explain_prompt, reconsider_prompt
from narrative_dag.schemas import ContextBundle, EditorJudgment


def judge_chat_router(mode: Literal["explain", "reconsider"]) -> Literal["explain", "reconsider"]:
    """Route to explain or reconsider based on explicit mode."""
    return mode


def _bundle_text(bundle: ContextBundle) -> str:
    prompt_ctx = PromptContext(
        target_chunk=bundle.target_chunk,
        previous_chunks=bundle.context_window.previous_chunks,
        next_chunks=bundle.context_window.next_chunks,
        global_summary=bundle.context_window.global_summary,
        plot_summary=getattr(bundle.document_state.plot_overview, "plot_summary", "") if bundle.document_state else "",
        story_point=getattr(bundle.document_state.plot_overview, "story_point", "") if bundle.document_state else "",
        stakes=getattr(bundle.document_state.plot_overview, "stakes", "") if bundle.document_state else "",
        theme_hypotheses=list(getattr(bundle.document_state.plot_overview, "theme_hypotheses", []) or [])
        if bundle.document_state
        else [],
        emotional_curve=list(bundle.document_state.emotional_curve) if bundle.document_state else [],
        narrative_map=list(bundle.document_state.narrative_map) if bundle.document_state else [],
        character_voice_map=dict(bundle.document_state.character_voice_map) if bundle.document_state else {},
        character_database=[
            c.model_dump() if hasattr(c, "model_dump") else c
            for c in list(getattr(getattr(bundle, "document_state", None), "character_database", {}).characters or [])
        ]
        if getattr(getattr(bundle, "document_state", None), "character_database", None)
        else [],
        genre_intention=bundle.genre_intention,
    )
    return (
        format_prompt_context(prompt_ctx)
        + "\n\nDetectors: "
        + repr(bundle.detector_results)
        + "\nCritic: "
        + repr(bundle.critic_result.model_dump() if bundle.critic_result else None)
        + "\nDefense: "
        + repr(bundle.defense_result.model_dump() if bundle.defense_result else None)
        + "\nDialectic mediation (if present): "
        + repr(bundle.dialectic_mediation.model_dump() if bundle.dialectic_mediation else None)
        + "\nDialectic synthesis (if present): "
        + repr(bundle.dialectic_synthesis.model_dump() if bundle.dialectic_synthesis else None)
        + "\nCurrent judgment: "
        + repr(bundle.current_judgment.model_dump() if bundle.current_judgment else None)
    )


def _state_llm(state: dict[str, Any]) -> Any:
    llm = state.get("_llm")
    return llm if llm is not None else llm_runtime.get_llm(stage="chat")


def judge_explainer(bundle: ContextBundle, user_message: str, llm: Any) -> str:
    """Clarify evidence, detector signals, and decision reasoning. Verdict unchanged."""
    prompt = explain_prompt(_bundle_text(bundle), user_message)
    response = llm.invoke([HumanMessage(content=prompt)])
    if isinstance(response, str):
        return response
    content = getattr(response, "content", "")
    return content if isinstance(content, str) else str(content)


def judge_reconsideration(bundle: ContextBundle, user_message: str, llm: Any) -> EditorJudgment:
    """Re-run judgment with full context bundle."""
    prompt = reconsider_prompt(_bundle_text(bundle), user_message)
    return structured_invoke(llm, [HumanMessage(content=prompt)], EditorJudgment)


def run_judge_explain(state: dict[str, Any]) -> dict[str, Any]:
    """Service-driven step: explain mode. Expects context_bundle, user_message, _llm."""
    bundle = state.get("context_bundle")
    msg = state.get("user_message", "")
    if not bundle:
        return {"chat_reply": "No context bundle for this chunk."}
    reply = judge_explainer(bundle, msg, _state_llm(state))
    return {"chat_reply": reply, "updated_judgment": None}


def run_judge_reconsider(state: dict[str, Any]) -> dict[str, Any]:
    """Service-driven step: reconsider mode. Expects context_bundle, user_message, _llm."""
    bundle = state.get("context_bundle")
    msg = state.get("user_message", "")
    if not bundle:
        return {"chat_reply": "No context bundle.", "updated_judgment": None}
    new_judgment = judge_reconsideration(bundle, msg, _state_llm(state))
    return {"chat_reply": "Reconsideration applied.", "updated_judgment": new_judgment}

