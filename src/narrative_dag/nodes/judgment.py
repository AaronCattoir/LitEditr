"""Judgment layer: editor_judge, elasticity_evaluator, report_collector."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import HumanMessage

import narrative_dag.llm as llm_runtime
from narrative_dag.llm import structured_invoke
from narrative_dag.prompt_context import build_prompt_context
from narrative_dag.prompts.judgment import editor_judgment_prompt, elasticity_prompt
from narrative_dag.evidence_fill import fill_judgment_spans
from narrative_dag.schemas import (
    ChunkJudgmentEntry,
    CriticResult,
    DefenseResult,
    EditorJudgment,
    ElasticityResult,
    EditorialReport,
)


def _state_llm(state: dict[str, Any]) -> Any:
    llm = state.get("_llm_judge") or state.get("_llm")
    return llm if llm is not None else llm_runtime.get_llm(stage="judgment")


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


def editor_judge(state: dict[str, Any]) -> dict[str, Any]:
    """Core node: final keep/cut/rewrite decision. Advisory only; no generated prose."""
    prompt_ctx = build_prompt_context(state)
    if prompt_ctx is None:
        return {"editor_judgment": EditorJudgment()}
    critic = state.get("critic_result")
    defense = state.get("defense_result")
    prompt = editor_judgment_prompt(
        prompt_ctx,
        _detector_snapshot(state),
        critic.model_dump_json() if hasattr(critic, "model_dump_json") else str(critic),
        defense.model_dump_json() if hasattr(defense, "model_dump_json") else str(defense),
    )
    result = structured_invoke(_state_llm(state), [HumanMessage(content=prompt)], EditorJudgment)
    result = fill_judgment_spans(state, result)
    return {"editor_judgment": result}


def elasticity_evaluator(state: dict[str, Any]) -> dict[str, Any]:
    """Assess intentional deviation and override drift only when justified."""
    prompt_ctx = build_prompt_context(state)
    if prompt_ctx is None:
        return {"elasticity_result": ElasticityResult()}
    judgment = state.get("editor_judgment")
    drift = state.get("drift_result")
    prompt = elasticity_prompt(
        prompt_ctx,
        judgment.model_dump_json() if hasattr(judgment, "model_dump_json") else str(judgment),
        drift.model_dump_json() if hasattr(drift, "model_dump_json") else str(drift),
    )
    result = structured_invoke(_state_llm(state), [HumanMessage(content=prompt)], ElasticityResult)
    return {"elasticity_result": result}


def report_collector(state: dict[str, Any]) -> dict[str, Any]:
    """Assemble per-chunk judgments into final EditorialReport. Expects chunk_judgments list and run_id."""
    run_id = state.get("run_id", "")
    chunk_judgments = state.get("chunk_judgments", [])
    if isinstance(chunk_judgments, list) and chunk_judgments and hasattr(chunk_judgments[0], "chunk_id"):
        entries = chunk_judgments
    else:
        entries = []
    document_summary = "Editorial report from narrative analysis."
    plot_overview = state.get("plot_overview")
    if not plot_overview and state.get("document_state"):
        plot_overview = getattr(state["document_state"], "plot_overview", None)
    if plot_overview and getattr(plot_overview, "story_point", "").strip():
        document_summary = f"Story context: {plot_overview.story_point.strip()}\n\n{document_summary}"
    report = EditorialReport(
        run_id=run_id,
        chunk_judgments=entries,
        document_summary=document_summary,
    )
    return {"editorial_report": report}


def _optional_critic(raw: Any) -> CriticResult | None:
    if raw is None:
        return None
    if isinstance(raw, CriticResult):
        return raw
    if isinstance(raw, dict):
        return CriticResult.model_validate(raw)
    return None


def _optional_defense(raw: Any) -> DefenseResult | None:
    if raw is None:
        return None
    if isinstance(raw, DefenseResult):
        return raw
    if isinstance(raw, dict):
        return DefenseResult.model_validate(raw)
    return None


def build_chunk_judgment_entry(
    chunk_id: str,
    position: int,
    judgment: EditorJudgment,
    elasticity: ElasticityResult | None,
    *,
    critic_result: Any = None,
    defense_result: Any = None,
) -> ChunkJudgmentEntry:
    """Helper to build one ChunkJudgmentEntry for report_collector."""
    return ChunkJudgmentEntry(
        chunk_id=chunk_id,
        position=position,
        judgment=judgment,
        elasticity=elasticity,
        critic_result=_optional_critic(critic_result),
        defense_result=_optional_defense(defense_result),
    )

