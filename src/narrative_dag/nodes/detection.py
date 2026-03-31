"""Detection layer: LLM-powered detectors."""

from __future__ import annotations

import sys
import time
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


def _log_detector(state: dict[str, Any], detector_name: str, msg: str) -> None:
    chunk_id = state.get("current_chunk_id") or "?"
    print(f"       detectors[{detector_name}] chunk={chunk_id} {msg}", file=sys.stderr, flush=True)


def _run_detector(
    state: dict[str, Any],
    *,
    detector_name: str,
    result_key: str,
    default_result: Any,
    schema: Any,
) -> dict[str, Any]:
    prompt = _detector_prompt(state, detector_name)
    if not prompt:
        _log_detector(state, detector_name, "skipped (no prompt context)")
        return {result_key: default_result}
    _log_detector(state, detector_name, "start")
    t0 = time.time()
    result = structured_invoke(
        _state_llm(state),
        [HumanMessage(content=prompt)],
        schema,
        trace_label=f"detector:{detector_name}",
    )
    _log_detector(state, detector_name, f"done {time.time()-t0:.1f}s")
    return {result_key: result}


def drift_detector(state: dict[str, Any]) -> dict[str, Any]:
    return _run_detector(
        state,
        detector_name="drift",
        result_key="drift_result",
        default_result=DriftResult(),
        schema=DriftResult,
    )


def cliche_detector(state: dict[str, Any]) -> dict[str, Any]:
    return _run_detector(
        state,
        detector_name="cliche",
        result_key="cliche_result",
        default_result=ClicheResult(),
        schema=ClicheResult,
    )


def vagueness_detector(state: dict[str, Any]) -> dict[str, Any]:
    return _run_detector(
        state,
        detector_name="vagueness",
        result_key="vagueness_result",
        default_result=VaguenessResult(),
        schema=VaguenessResult,
    )


def emotional_honesty_detector(state: dict[str, Any]) -> dict[str, Any]:
    return _run_detector(
        state,
        detector_name="emotional_honesty",
        result_key="emotional_honesty_result",
        default_result=EmotionalHonestyResult(),
        schema=EmotionalHonestyResult,
    )


def redundancy_detector(state: dict[str, Any]) -> dict[str, Any]:
    return _run_detector(
        state,
        detector_name="redundancy",
        result_key="redundancy_result",
        default_result=RedundancyResult(),
        schema=RedundancyResult,
    )


def risk_detector(state: dict[str, Any]) -> dict[str, Any]:
    return _run_detector(
        state,
        detector_name="risk",
        result_key="risk_result",
        default_result=RiskResult(),
        schema=RiskResult,
    )


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

