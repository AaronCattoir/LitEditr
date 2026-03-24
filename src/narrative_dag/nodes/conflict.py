"""Conflict layer: critic_agent then defense_agent (LLM-backed)."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import HumanMessage

import narrative_dag.llm as llm_runtime
from narrative_dag.llm import structured_invoke
from narrative_dag.prompt_context import build_prompt_context
from narrative_dag.prompts.conflict import critic_prompt, defense_prompt
from narrative_dag.evidence_fill import fill_critic_spans, fill_defense_spans
from narrative_dag.schemas import CriticResult, DefenseResult


def _state_llm(state: dict[str, Any]) -> Any:
    llm = state.get("_llm_judge") or state.get("_llm")
    return llm if llm is not None else llm_runtime.get_llm()


def _detector_snapshot(state: dict[str, Any]) -> str:
    keys = [
        "drift_result",
        "cliche_result",
        "vagueness_result",
        "emotional_honesty_result",
        "redundancy_result",
        "risk_result",
    ]
    parts: list[str] = []
    for key in keys:
        value = state.get(key)
        if hasattr(value, "model_dump"):
            parts.append(f"{key}: {value.model_dump()}")
    return "\n".join(parts)


def critic_agent(state: dict[str, Any]) -> dict[str, Any]:
    """Produce critique from chunk + detector outputs."""
    prompt_ctx = build_prompt_context(state)
    if prompt_ctx is None:
        return {"critic_result": CriticResult()}
    prompt = critic_prompt(prompt_ctx, _detector_snapshot(state))
    result = structured_invoke(_state_llm(state), [HumanMessage(content=prompt)], CriticResult)
    result = fill_critic_spans(state, result)
    return {"critic_result": result}


def defense_agent(state: dict[str, Any]) -> dict[str, Any]:
    """Produce defense response given critic output and same evidence."""
    prompt_ctx = build_prompt_context(state)
    if prompt_ctx is None:
        return {"defense_result": DefenseResult()}
    critic = state.get("critic_result")
    critic_text = critic.model_dump_json() if hasattr(critic, "model_dump_json") else str(critic)
    prompt = defense_prompt(prompt_ctx, _detector_snapshot(state), critic_text)
    result = structured_invoke(_state_llm(state), [HumanMessage(content=prompt)], DefenseResult)
    result = fill_defense_spans(state, result)
    return {"defense_result": result}

