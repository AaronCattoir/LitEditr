"""Top-level StateGraph wiring: ingestion -> representation -> detection -> conflict -> judgment -> report."""

from __future__ import annotations

import sys
import time
from typing import Any, Callable

from langgraph.graph import END, StateGraph

import narrative_dag.llm as llm_runtime
from narrative_dag.nodes.ingestion import run_chunker, run_context_builder
from narrative_dag.nodes.plot_overview import plot_overview_builder
from narrative_dag.nodes.character_map import character_map_builder
from narrative_dag.nodes.representation import (
    paragraph_analyzer,
    voice_profiler,
    run_document_state_builder,
)
from narrative_dag.nodes.detection import run_all_detectors
from narrative_dag.nodes.conflict import critic_agent, defense_agent
from narrative_dag.nodes.judgment import (
    editor_judge,
    elasticity_evaluator,
    report_collector,
    build_chunk_judgment_entry,
)
from narrative_dag.schemas import (
    ChunkJudgmentEntry,
    GenreIntention,
    RawDocument,
)


def build_chunk_pipeline_graph():
    """Build the per-chunk pipeline: context -> analysis -> document_state -> detectors -> critic -> defense -> judge -> elasticity."""
    builder = StateGraph(dict)

    builder.add_node("context_builder", run_context_builder)
    builder.add_node("paragraph_analyzer", paragraph_analyzer)
    builder.add_node("voice_profiler", voice_profiler)
    builder.add_node("document_state_builder", run_document_state_builder)
    builder.add_node("detectors", run_all_detectors)
    builder.add_node("critic", critic_agent)
    builder.add_node("defense", defense_agent)
    builder.add_node("editor_judge", editor_judge)
    builder.add_node("elasticity", elasticity_evaluator)

    builder.set_entry_point("context_builder")
    builder.add_edge("context_builder", "paragraph_analyzer")
    builder.add_edge("paragraph_analyzer", "voice_profiler")
    builder.add_edge("voice_profiler", "document_state_builder")
    builder.add_edge("document_state_builder", "detectors")
    builder.add_edge("detectors", "critic")
    builder.add_edge("critic", "defense")
    builder.add_edge("defense", "editor_judge")
    builder.add_edge("editor_judge", "elasticity")
    builder.add_edge("elasticity", END)

    return builder.compile()


def run_analysis(
    raw_document: RawDocument,
    genre_intention: GenreIntention,
    run_id: str,
    *,
    db_path: str | None = None,
    on_chunk_done: (
        Callable[[str, str, int, dict, Any, Any], None] | None
    ) = None,
) -> tuple[dict[str, Any], list[ChunkJudgmentEntry]]:
    """Run full analysis: chunker, then per-chunk pipeline, then report.
    on_chunk_done(run_id, chunk_id, position, artifact_dict, judgment, elasticity) called after each chunk.
    """
    def _log(msg: str) -> None:
        print(msg, file=sys.stderr, flush=True)

    t0 = time.time()

    _log("[init] creating LLM clients (default/detector/judgment)...")
    llm = llm_runtime.get_llm()
    llm_detector = llm_runtime.get_llm(stage="detector")
    llm_judge = llm_runtime.get_llm(stage="judgment")
    state: dict[str, Any] = {
        "raw_document": raw_document,
        "genre_intention": genre_intention,
        "run_id": run_id,
        "chunks": [],
        "chunk_judgments": [],
        "document_state": None,
        "_llm": llm,
        "_llm_detector": llm_detector,
        "_llm_judge": llm_judge,
    }

    # 1) Chunker
    _log("[1/5] chunking document...")
    state = {**state, **run_chunker(state)}

    chunks = state.get("chunks") or []
    if not chunks:
        state["editorial_report"] = {"run_id": run_id, "chunk_judgments": [], "document_summary": "No chunks."}
        return state, []
    _log(f"[1/5] found {len(chunks)} chunks ({time.time()-t0:.1f}s)")

    # 2) Plot overview (global story context)
    _log("[2/6] building plot overview...")
    state = {**state, **plot_overview_builder(state)}
    state["global_summary"] = (
        state["plot_overview"].plot_summary if state.get("plot_overview") else ""
    )
    _log(f"[2/6] plot overview done ({time.time()-t0:.1f}s)")

    # 3) Character map from full document.
    _log("[3/6] building character database...")
    state = {**state, **character_map_builder(state)}
    _log(f"[3/6] character database done ({time.time()-t0:.1f}s)")

    # 4) Document state baseline from first chunk (calibration)
    _log("[4/6] calibrating on first chunk...")
    state["current_chunk_id"] = chunks[0].id
    state = {**state, **run_context_builder(state)}
    state = {**state, **paragraph_analyzer(state)}
    state = {**state, **voice_profiler(state)}
    state = {**state, **run_document_state_builder(state)}
    doc_state = state.get("document_state")
    _log(f"[4/6] calibration done ({time.time()-t0:.1f}s)")

    # 5) Per-chunk pipeline
    chunk_judgments: list[ChunkJudgmentEntry] = []
    for i, ch in enumerate(chunks):
        _log(f"[5/6] chunk {i+1}/{len(chunks)} ({ch.id})...")
        chunk_t0 = time.time()
        st = {
            "chunks": chunks,
            "current_chunk_id": ch.id,
            "global_summary": state.get("global_summary", ""),
            "genre_intention": genre_intention,
            "document_state": doc_state,
            "character_database": state.get("character_database"),
            "chunk_judgments": chunk_judgments,
            "plot_overview": state.get("plot_overview"),
            "_llm": llm,
            "_llm_detector": llm_detector,
            "_llm_judge": llm_judge,
        }
        steps = [
            ("context",    run_context_builder),
            ("analysis",   paragraph_analyzer),
            ("voice",      voice_profiler),
            ("doc_state",  run_document_state_builder),
            ("detectors",  run_all_detectors),
            ("critic",     critic_agent),
            ("defense",    defense_agent),
            ("judge",      editor_judge),
            ("elasticity", elasticity_evaluator),
        ]
        for step_name, step_fn in steps:
            step_t = time.time()
            st = {**st, **step_fn(st)}
            _log(f"       {step_name} {time.time()-step_t:.1f}s")
        _log(f"[5/6] chunk {i+1}/{len(chunks)} done ({time.time()-chunk_t0:.1f}s, total {time.time()-t0:.1f}s)")
        judgment = st.get("editor_judgment")
        elasticity = st.get("elasticity_result")
        if judgment:
            entry = build_chunk_judgment_entry(ch.id, i, judgment, elasticity)
            chunk_judgments.append(entry)
        doc_state = st.get("document_state") or doc_state
        if on_chunk_done and judgment is not None:
            def _dump(x):
                return x.model_dump() if hasattr(x, "model_dump") else x
            artifact = {
                "target_chunk": ch.model_dump(),
                "context_window": (
                    {
                        "target_chunk": st["context_window"].target_chunk.model_dump(),
                        "previous_chunks": [c.model_dump() for c in st["context_window"].previous_chunks],
                        "next_chunks": [c.model_dump() for c in st["context_window"].next_chunks],
                        "global_summary": getattr(st["context_window"], "global_summary", ""),
                    }
                    if st.get("context_window") and hasattr(st["context_window"], "target_chunk")
                    else {"target_chunk": ch.model_dump(), "previous_chunks": [], "next_chunks": [], "global_summary": ""}
                ),
                "detector_results": {
                    "drift": _dump(st["drift_result"]) if st.get("drift_result") else None,
                    "cliche": _dump(st["cliche_result"]) if st.get("cliche_result") else None,
                    "vagueness": _dump(st["vagueness_result"]) if st.get("vagueness_result") else None,
                    "emotional_honesty": _dump(st["emotional_honesty_result"]) if st.get("emotional_honesty_result") else None,
                    "redundancy": _dump(st["redundancy_result"]) if st.get("redundancy_result") else None,
                    "risk": _dump(st["risk_result"]) if st.get("risk_result") else None,
                },
                "critic_result": _dump(st["critic_result"]) if st.get("critic_result") else None,
                "defense_result": _dump(st["defense_result"]) if st.get("defense_result") else None,
                "character_database": _dump(st["character_database"]) if st.get("character_database") else None,
                "current_judgment": judgment.model_dump(),
            }
            on_chunk_done(run_id, ch.id, i, artifact, judgment, elasticity)

    # 6) Report
    _log(f"[6/6] building report...")
    state["run_id"] = run_id
    state["chunk_judgments"] = chunk_judgments
    state = {**state, **report_collector(state)}
    _log(f"[done] analysis complete ({time.time()-t0:.1f}s)")

    return state, chunk_judgments
