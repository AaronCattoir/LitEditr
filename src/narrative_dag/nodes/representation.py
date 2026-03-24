"""Representation layer: LLM-powered narrative understanding."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import HumanMessage

from narrative_dag.config import DEFAULT_CALIBRATION_CHUNKS, get_genre_profile
import narrative_dag.llm as llm_runtime
from narrative_dag.llm import structured_invoke
from narrative_dag.prompt_context import build_prompt_context
from narrative_dag.prompts.representation import (
    dialogue_analysis_prompt,
    paragraph_analysis_prompt,
    voice_profile_prompt,
)
from narrative_dag.schemas import (
    AllowedVariance,
    CharacterDatabase,
    ContextWindow,
    DialogueAnalysis,
    DocumentState,
    ParagraphAnalysis,
    PlotOverview,
    VoiceProfile,
)


def _state_llm(state: dict[str, Any]) -> Any:
    llm = state.get("_llm")
    return llm if llm is not None else llm_runtime.get_llm()


def _genre_str(state: dict[str, Any]) -> str:
    genre_intention = state.get("genre_intention")
    if hasattr(genre_intention, "genre"):
        return genre_intention.genre or "literary_fiction"
    if isinstance(genre_intention, dict):
        return genre_intention.get("genre", "literary_fiction")
    return "literary_fiction"


def paragraph_analyzer(state: dict[str, Any]) -> dict[str, Any]:
    """Analyze target chunk into ParagraphAnalysis via LLM structured output."""
    ctx = state.get("context_window")
    if not ctx:
        return {}
    if isinstance(ctx, dict):
        ctx = ContextWindow.model_validate(ctx)
    llm = _state_llm(state)
    prompt_ctx = build_prompt_context(state)
    if prompt_ctx is None:
        return {}
    prompt = paragraph_analysis_prompt(prompt_ctx)
    analysis = structured_invoke(llm, [HumanMessage(content=prompt)], ParagraphAnalysis)
    return {"paragraph_analysis": analysis}


def voice_profiler(state: dict[str, Any]) -> dict[str, Any]:
    """Extract structured voice profile via LLM."""
    ctx = state.get("context_window")
    analysis = state.get("paragraph_analysis")
    if not ctx or not analysis:
        return {}
    if isinstance(ctx, dict):
        ctx = ContextWindow.model_validate(ctx)
    if isinstance(analysis, dict):
        analysis = ParagraphAnalysis.model_validate(analysis)
    llm = _state_llm(state)
    prompt_ctx = build_prompt_context(state)
    if prompt_ctx is None:
        return {}
    prompt = voice_profile_prompt(prompt_ctx, paragraph_intent=analysis.intent)
    profile = structured_invoke(llm, [HumanMessage(content=prompt)], VoiceProfile)
    return {"voice_profile": profile}


def dialogue_analyzer(state: dict[str, Any]) -> dict[str, Any] | None:
    """Track character voice consistency via LLM."""
    ctx = state.get("context_window")
    if not ctx:
        return None
    if isinstance(ctx, dict):
        ctx = ContextWindow.model_validate(ctx)
    llm = _state_llm(state)
    prompt_ctx = build_prompt_context(state)
    if prompt_ctx is None:
        return None
    prompt = dialogue_analysis_prompt(prompt_ctx)
    result = structured_invoke(llm, [HumanMessage(content=prompt)], DialogueAnalysis)
    return {"dialogue_analysis": result}


def document_state_builder(
    state: dict[str, Any],
    calibration_chunks: int = DEFAULT_CALIBRATION_CHUNKS,
) -> dict[str, Any]:
    """Aggregate global editor memory from current features and rolling state."""
    genre_str = _genre_str(state)
    profile = get_genre_profile(genre_str)
    prior_doc_state = state.get("document_state")
    if isinstance(prior_doc_state, dict):
        prior_doc_state = DocumentState.model_validate(prior_doc_state)
    if not isinstance(prior_doc_state, DocumentState):
        prior_doc_state = DocumentState()

    voice_baseline = state.get("voice_profile") or prior_doc_state.voice_baseline or {}
    if isinstance(voice_baseline, dict) and voice_baseline:
        voice_baseline = VoiceProfile.model_validate(voice_baseline)

    emotional_curve = list(prior_doc_state.emotional_curve)
    emotional_curve.extend(list(state.get("emotional_curve", [])))
    pa = state.get("paragraph_analysis")
    if isinstance(pa, dict):
        pa = ParagraphAnalysis.model_validate(pa)
    if isinstance(pa, ParagraphAnalysis):
        emotional_curve.append({"chunk_id": state.get("current_chunk_id", ""), "register": pa.emotional_register})
    emotional_curve = emotional_curve[-calibration_chunks:]

    narrative_map = list(prior_doc_state.narrative_map)
    narrative_map.extend(list(state.get("narrative_map", [])))
    ctx = state.get("context_window")
    if isinstance(ctx, dict):
        ctx = ContextWindow.model_validate(ctx)
    if isinstance(ctx, ContextWindow):
        narrative_map.append({"chunk_id": ctx.target_chunk.id, "intent": getattr(pa, "intent", "")})
    narrative_map = narrative_map[-100:]

    character_voice_map = dict(prior_doc_state.character_voice_map)
    character_voice_map.update(dict(state.get("character_voice_map", {})))
    da = state.get("dialogue_analysis")
    if isinstance(da, dict):
        da = DialogueAnalysis.model_validate(da)
    if isinstance(da, DialogueAnalysis) and da.speaker:
        character_voice_map[da.speaker] = da.style_features

    bounds = {
        "formality": {
            "min": max(0.0, 0.3 - profile.drift_sensitivity * 0.2),
            "max": min(1.0, 0.7 + profile.drift_sensitivity * 0.2),
        },
        "distance": {"min": 0.0, "max": 1.0},
    }
    allowed_variance = AllowedVariance(bounds=bounds)

    plot_overview = state.get("plot_overview") or prior_doc_state.plot_overview
    if isinstance(plot_overview, dict):
        plot_overview = PlotOverview.model_validate(plot_overview)
    character_database = state.get("character_database") or prior_doc_state.character_database
    if isinstance(character_database, dict):
        character_database = CharacterDatabase.model_validate(character_database)

    doc_state = DocumentState(
        voice_baseline=voice_baseline,
        emotional_curve=emotional_curve,
        narrative_map=narrative_map,
        character_voice_map=character_voice_map,
        allowed_variance=allowed_variance,
        genre_intention=state.get("genre_intention"),
        plot_overview=plot_overview,
        character_database=character_database,
    )
    return {"document_state": doc_state}


def run_document_state_builder(state: dict[str, Any]) -> dict[str, Any]:
    """LangGraph node wrapper for document_state_builder."""
    return document_state_builder(state)

