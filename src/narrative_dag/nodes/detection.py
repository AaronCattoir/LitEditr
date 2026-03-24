"""Detection layer: LLM-powered detectors."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import HumanMessage

import narrative_dag.llm as llm_runtime
from narrative_dag.llm import structured_invoke
from narrative_dag.prompt_context import build_prompt_context
from narrative_dag.prompts.detection import detector_prompt
from narrative_dag.schemas import (
    ClicheResult,
    DriftResult,
    EmotionalHonestyResult,
    ParagraphAnalysis,
    RedundancyResult,
    RiskResult,
    VaguenessResult,
    VoiceProfile,
)


def _state_llm(state: dict[str, Any]) -> Any:
    llm = state.get("_llm_detector") or state.get("_llm")
    return llm if llm is not None else llm_runtime.get_llm()


def _detector_prompt(state: dict[str, Any], detector_name: str) -> str | None:
    prompt_ctx = build_prompt_context(state)
    if prompt_ctx is None:
        return None

    analysis = state.get("paragraph_analysis")
    if isinstance(analysis, dict):
        analysis = ParagraphAnalysis.model_validate(analysis)
    voice_profile = state.get("voice_profile")
    if isinstance(voice_profile, dict):
        voice_profile = VoiceProfile.model_validate(voice_profile)

    return detector_prompt(
        detector_name,
        prompt_ctx,
        paragraph_intent=getattr(analysis, "intent", ""),
        voice_profile=voice_profile.model_dump() if hasattr(voice_profile, "model_dump") else None,
    )


def drift_detector(state: dict[str, Any]) -> dict[str, Any]:
    prompt = _detector_prompt(state, "drift")
    if not prompt:
        return {"drift_result": DriftResult()}
    result = structured_invoke(_state_llm(state), [HumanMessage(content=prompt)], DriftResult)
    return {"drift_result": result}


def cliche_detector(state: dict[str, Any]) -> dict[str, Any]:
    prompt = _detector_prompt(state, "cliche")
    if not prompt:
        return {"cliche_result": ClicheResult()}
    result = structured_invoke(_state_llm(state), [HumanMessage(content=prompt)], ClicheResult)
    return {"cliche_result": result}


def vagueness_detector(state: dict[str, Any]) -> dict[str, Any]:
    prompt = _detector_prompt(state, "vagueness")
    if not prompt:
        return {"vagueness_result": VaguenessResult()}
    result = structured_invoke(_state_llm(state), [HumanMessage(content=prompt)], VaguenessResult)
    return {"vagueness_result": result}


def emotional_honesty_detector(state: dict[str, Any]) -> dict[str, Any]:
    prompt = _detector_prompt(state, "emotional_honesty")
    if not prompt:
        return {"emotional_honesty_result": EmotionalHonestyResult()}
    result = structured_invoke(_state_llm(state), [HumanMessage(content=prompt)], EmotionalHonestyResult)
    return {"emotional_honesty_result": result}


def redundancy_detector(state: dict[str, Any]) -> dict[str, Any]:
    prompt = _detector_prompt(state, "redundancy")
    if not prompt:
        return {"redundancy_result": RedundancyResult()}
    result = structured_invoke(_state_llm(state), [HumanMessage(content=prompt)], RedundancyResult)
    return {"redundancy_result": result}


def risk_detector(state: dict[str, Any]) -> dict[str, Any]:
    prompt = _detector_prompt(state, "risk")
    if not prompt:
        return {"risk_result": RiskResult()}
    result = structured_invoke(_state_llm(state), [HumanMessage(content=prompt)], RiskResult)
    return {"risk_result": result}


def run_all_detectors(state: dict[str, Any]) -> dict[str, Any]:
    """Run all detector nodes and merge outputs."""
    out: dict[str, Any] = {}
    out.update(drift_detector(state))
    out.update(cliche_detector(state))
    out.update(vagueness_detector(state))
    out.update(emotional_honesty_detector(state))
    out.update(redundancy_detector(state))
    out.update(risk_detector(state))
    return out

