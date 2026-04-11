"""Dialectic mediator and synthesis nodes (internal; before editor_judge)."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import HumanMessage

import narrative_dag.llm as llm_runtime
from narrative_dag.llm import structured_invoke
from narrative_dag.prompt_context import build_prompt_context
from narrative_dag.prompts.dialectic import dialectic_mediation_prompt, dialectic_synthesis_prep_prompt
from narrative_dag.schemas import DialecticMediationResult, DialecticSynthesisResult


def _state_llm(state: dict[str, Any]) -> Any:
    llm = state.get("_llm_judge") or state.get("_llm")
    return llm if llm is not None else llm_runtime.get_llm(stage="judgment")


def dialectic_mediator(state: dict[str, Any]) -> dict[str, Any]:
    """Step 3: impartial analysis of critic vs advocate (no final verdict)."""
    prompt_ctx = build_prompt_context(state)
    if prompt_ctx is None:
        return {"dialectic_mediation": DialecticMediationResult()}
    critic = state.get("critic_result")
    defense = state.get("defense_result")
    prompt = dialectic_mediation_prompt(
        prompt_ctx,
        critic.model_dump_json() if hasattr(critic, "model_dump_json") else str(critic),
        defense.model_dump_json() if hasattr(defense, "model_dump_json") else str(defense),
    )
    result = structured_invoke(_state_llm(state), [HumanMessage(content=prompt)], DialecticMediationResult)
    return {"dialectic_mediation": result}


def dialectic_synthesizer(state: dict[str, Any]) -> dict[str, Any]:
    """Step 4: higher-level synthesis after mediation (deep depth)."""
    prompt_ctx = build_prompt_context(state)
    if prompt_ctx is None:
        return {"dialectic_synthesis": DialecticSynthesisResult()}
    mediation = state.get("dialectic_mediation")
    critic = state.get("critic_result")
    defense = state.get("defense_result")
    med_json = mediation.model_dump_json() if hasattr(mediation, "model_dump_json") else str(mediation)
    prompt = dialectic_synthesis_prep_prompt(
        prompt_ctx,
        critic.model_dump_json() if hasattr(critic, "model_dump_json") else str(critic),
        defense.model_dump_json() if hasattr(defense, "model_dump_json") else str(defense),
        med_json,
    )
    result = structured_invoke(_state_llm(state), [HumanMessage(content=prompt)], DialecticSynthesisResult)
    return {"dialectic_synthesis": result}
