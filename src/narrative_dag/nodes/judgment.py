"""Judgment layer: editor_judge, elasticity_evaluator, report_collector."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import HumanMessage

import narrative_dag.llm as llm_runtime
from narrative_dag.llm import structured_invoke
from narrative_dag.prompt_context import build_prompt_context
from narrative_dag.prompts.judgment import editor_judgment_prompt, elasticity_prompt, evidence_synthesis_prompt
from narrative_dag.evidence_fill import fill_judgment_spans
from narrative_dag.schemas import (
    ChunkJudgmentEntry,
    CriticResult,
    DefenseResult,
    EditorJudgment,
    ElasticityResult,
    EditorialReport,
    EvidenceSynthesisResult,
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


def _tighten_local_span(chunk_text: str, start: int, end: int, *, max_chars: int = 140) -> tuple[int, int]:
    """Trim noisy edges and cap very long matches for cleaner UI highlights."""
    n = len(chunk_text)
    s = max(0, min(start, n))
    e = max(0, min(end, n))
    if e <= s:
        return s, e

    # Trim surrounding whitespace.
    while s < e and chunk_text[s].isspace():
        s += 1
    while e > s and chunk_text[e - 1].isspace():
        e -= 1
    if e <= s:
        return start, end

    # Keep highlights reasonably tight when extraction returns long phrases.
    if (e - s) > max_chars:
        hard = s + max_chars
        cut = hard
        for i in range(hard, s + 40, -1):
            if chunk_text[i - 1] in ".!?;:,":
                cut = i
                break
        e = max(s + 20, cut)

    # Snap to whole-word boundaries so UI never highlights half a word.
    while s > 0 and not chunk_text[s - 1].isspace() and chunk_text[s - 1] not in "\"'“”‘’.,!?;:()[]{}":
        s -= 1
    while e < n and not chunk_text[e].isspace() and chunk_text[e] not in "\"'“”‘’.,!?;:()[]{}":
        e += 1
    return s, e


def _norm_space(s: str) -> str:
    return " ".join((s or "").split()).strip()


def editor_judge(state: dict[str, Any]) -> dict[str, Any]:
    """Core node: final keep/cut/rewrite decision. Advisory only; no generated prose."""
    prompt_ctx = build_prompt_context(state)
    if prompt_ctx is None:
        return {"editor_judgment": EditorJudgment()}
    critic = state.get("critic_result")
    defense = state.get("defense_result")
    dm = state.get("dialectic_mediation")
    ds = state.get("dialectic_synthesis")
    mediation_s = dm.model_dump_json() if dm is not None and hasattr(dm, "model_dump_json") else None
    synthesis_s = ds.model_dump_json() if ds is not None and hasattr(ds, "model_dump_json") else None
    prompt = editor_judgment_prompt(
        prompt_ctx,
        _detector_snapshot(state),
        critic.model_dump_json() if hasattr(critic, "model_dump_json") else str(critic),
        defense.model_dump_json() if hasattr(defense, "model_dump_json") else str(defense),
        dialectic_mediation=mediation_s,
        dialectic_synthesis=synthesis_s,
    )
    result = structured_invoke(_state_llm(state), [HumanMessage(content=prompt)], EditorJudgment)
    result = fill_judgment_spans(state, result)
    return {"editor_judgment": result}


def evidence_synthesizer(state: dict[str, Any]) -> dict[str, Any]:
    """Lightweight synthesis of critic/defense mapped to specific text spans."""
    prompt_ctx = build_prompt_context(state)
    if prompt_ctx is None:
        return {"evidence_synthesis_result": EvidenceSynthesisResult()}
    
    critic = state.get("critic_result")
    defense = state.get("defense_result")
    prompt = evidence_synthesis_prompt(
        prompt_ctx,
        critic.model_dump_json() if hasattr(critic, "model_dump_json") else str(critic),
        defense.model_dump_json() if hasattr(defense, "model_dump_json") else str(defense),
    )
    # Fast model is fine for this extraction task
    llm = state.get("_llm_detector") or _state_llm(state)
    result = structured_invoke(llm, [HumanMessage(content=prompt)], EvidenceSynthesisResult)
    
    # Map quotes to absolute chunk offsets
    chunk_text = prompt_ctx.target_chunk.text
    base_offset = prompt_ctx.target_chunk.start_char
    
    from narrative_dag.evidence_fill import _phrase_candidates
    
    valid_spans = []
    for span in result.spans:
        q = span.quote.strip()
        if not q:
            continue
        
        found_start = -1
        found_end = -1
        
        # Prefer model-provided local offsets when valid and matching.
        if span.end_char > span.start_char:
            ls = int(span.start_char)
            le = int(span.end_char)
            if 0 <= ls < le <= len(chunk_text):
                candidate = chunk_text[ls:le]
                if _norm_space(candidate).lower() == _norm_space(q).lower() or _norm_space(q).lower() in _norm_space(candidate).lower():
                    found_start = ls
                    found_end = le

        # Exact quote fallback.
        if found_start < 0:
            idx = chunk_text.find(q)
            if idx >= 0:
                found_start = idx
                found_end = idx + len(q)

        # Fuzzy fallback: prefer the shortest candidate that can be found.
        if found_start < 0:
            cands = [c for c in _phrase_candidates([q]) if c]
            cands.sort(key=len)
            for cand in cands:
                idx = chunk_text.find(cand)
                if idx >= 0:
                    found_start = idx
                    found_end = idx + len(cand)
                    break
                    
        if found_start >= 0:
            local_s, local_e = _tighten_local_span(chunk_text, found_start, found_end)
            if local_e <= local_s:
                continue
            span.start_char = base_offset + local_s
            span.end_char = base_offset + local_e
            span.quote = chunk_text[local_s:local_e]
            valid_spans.append(span)
            
    result.spans = valid_spans
    return {"evidence_synthesis_result": result}


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


def _optional_synthesis(raw: Any) -> EvidenceSynthesisResult | None:
    if raw is None:
        return None
    if isinstance(raw, EvidenceSynthesisResult):
        return raw
    if isinstance(raw, dict):
        return EvidenceSynthesisResult.model_validate(raw)
    return None


def build_chunk_judgment_entry(
    chunk_id: str,
    position: int,
    judgment: EditorJudgment,
    elasticity: ElasticityResult | None,
    *,
    critic_result: Any = None,
    defense_result: Any = None,
    evidence_synthesis_result: Any = None,
) -> ChunkJudgmentEntry:
    """Helper to build one ChunkJudgmentEntry for report_collector."""
    return ChunkJudgmentEntry(
        chunk_id=chunk_id,
        position=position,
        judgment=judgment,
        elasticity=elasticity,
        critic_result=_optional_critic(critic_result),
        defense_result=_optional_defense(defense_result),
        evidence_synthesis=_optional_synthesis(evidence_synthesis_result),
    )

