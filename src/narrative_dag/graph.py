"""Full-document analysis orchestration: chunking, global context, then per-chunk pipeline (imperative loop)."""

from __future__ import annotations

import sys
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

import narrative_dag.llm as llm_runtime
from narrative_dag.llm import RunLLMBundle
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
    evidence_synthesizer,
    report_collector,
    build_chunk_judgment_entry,
)
from narrative_dag.schemas import (
    Chunk,
    ChunkJudgmentEntry,
    DocumentState,
    GenreIntention,
    RawDocument,
)


def _replay_representation_for_chunk(base: dict[str, Any], ch: Chunk) -> dict[str, Any]:
    """Advance document_state through context / paragraph / voice / doc_state only (no detectors / judge)."""
    st = {**base, "current_chunk_id": ch.id}
    st = {**st, **run_context_builder(st)}
    st = {**st, **paragraph_analyzer(st)}
    st = {**st, **voice_profiler(st)}
    st = {**st, **run_document_state_builder(st)}
    return st


def run_analysis(
    raw_document: RawDocument,
    genre_intention: GenreIntention,
    run_id: str,
    *,
    db_path: str | None = None,
    on_chunk_done: (
        Callable[[str, str, int, dict, Any, Any], None] | None
    ) = None,
    only_chunk_ids: set[str] | None = None,
    client_chunks: list[Chunk] | None = None,
    seed_document_state: DocumentState | None = None,
    bundle: RunLLMBundle | None = None,
) -> tuple[dict[str, Any], list[ChunkJudgmentEntry]]:
    """Run full analysis: chunker (or pre-built client chunks), then per-chunk pipeline, then report.
    on_chunk_done(run_id, chunk_id, position, artifact_dict, judgment, elasticity) called after each chunk.
    If client_chunks is provided and non-empty, run_chunker is skipped.
    """
    def _log(msg: str) -> None:
        print(msg, file=sys.stderr, flush=True)

    t0 = time.time()

    _log("[init] creating LLM clients (default/detector/judgment)...")
    if bundle is not None:
        llm = bundle.llm
        llm_detector = bundle.llm_detector
        llm_judge = bundle.llm_judge
    else:
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

    # 1) Chunker or client-provided chunks
    if client_chunks:
        _log("[1/5] using client-defined chunks...")
        state["chunks"] = client_chunks
    else:
        _log("[1/5] chunking document...")
        state = {**state, **run_chunker(state)}

    chunks = state.get("chunks") or []
    if not chunks:
        state["editorial_report"] = {"run_id": run_id, "chunk_judgments": [], "document_summary": "No chunks."}
        return state, []
    _log(f"[1/5] found {len(chunks)} chunks ({time.time()-t0:.1f}s)")

    # 2–3) Plot overview + character database in parallel (wall ~ max of two LLM calls).
    # character_map_builder reads plot_overview from state; workers start before plot merges, so
    # plot_summary/story_point in the character prompt are empty for this call (latency vs. prompt).
    _log("[2/6] plot overview + character database (parallel)...")
    t_global = time.time()
    with ThreadPoolExecutor(max_workers=2) as pool:
        fut_plot = pool.submit(plot_overview_builder, state)
        fut_char = pool.submit(character_map_builder, state)
        plot_out = fut_plot.result()
        char_out = fut_char.result()
    state = {**state, **plot_out, **char_out}
    state["global_summary"] = (
        state["plot_overview"].plot_summary if state.get("plot_overview") else ""
    )
    _log(f"[2/6] plot + character DB wall {time.time() - t_global:.1f}s (total {time.time()-t0:.1f}s)")

    # 4) Document state baseline: full run calibrates on first chunk; partial runs may seed from base
    # and replay representation for chunks before the first target so middle inserts see coherent context.
    first_target_idx = 0
    if only_chunk_ids:
        idxs = [i for i, c in enumerate(chunks) if c.id in only_chunk_ids]
        if idxs:
            first_target_idx = min(idxs)

    base_for_replay: dict[str, Any] = {
        "raw_document": raw_document,
        "chunks": chunks,
        "genre_intention": genre_intention,
        "global_summary": state.get("global_summary", ""),
        "plot_overview": state.get("plot_overview"),
        "character_database": state.get("character_database"),
        "_llm": llm,
        "_llm_detector": llm_detector,
        "_llm_judge": llm_judge,
    }

    doc_state: DocumentState | None
    if only_chunk_ids and seed_document_state is not None:
        _log("[4/6] seeding document_state from base run + replaying preceding chunks...")
        doc_state = seed_document_state.model_copy(deep=True)
        state["document_state"] = doc_state
        for i in range(0, first_target_idx):
            _log(f"[4/6] replay representation {i + 1}/{first_target_idx} ({chunks[i].id})...")
            rep = {**base_for_replay, "document_state": doc_state}
            rep = _replay_representation_for_chunk(rep, chunks[i])
            doc_state = rep.get("document_state") or doc_state
        state["document_state"] = doc_state
        _log(f"[4/6] seed + replay done ({time.time()-t0:.1f}s)")
    else:
        _log("[4/6] calibrating on first chunk...")
        state["current_chunk_id"] = chunks[0].id
        state = {**state, **run_context_builder(state)}
        state = {**state, **paragraph_analyzer(state)}
        state = {**state, **voice_profiler(state)}
        state = {**state, **run_document_state_builder(state)}
        doc_state = state.get("document_state")
        if only_chunk_ids and first_target_idx > 1:
            for i in range(1, first_target_idx):
                _log(f"[4/6] replay representation before partial targets ({chunks[i].id})...")
                rep = {**base_for_replay, "document_state": doc_state}
                rep = _replay_representation_for_chunk(rep, chunks[i])
                doc_state = rep.get("document_state") or doc_state
            state["document_state"] = doc_state
        _log(f"[4/6] calibration done ({time.time()-t0:.1f}s)")

    # 5) Per-chunk pipeline
    chunk_judgments: list[ChunkJudgmentEntry] = []
    for i, ch in enumerate(chunks):
        if only_chunk_ids is not None and ch.id not in only_chunk_ids:
            continue
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
        ]
        for step_name, step_fn in steps:
            step_t = time.time()
            st = {**st, **step_fn(st)}
            _log(f"       {step_name} {time.time()-step_t:.1f}s")
            
        # Parallel judge and evidence synthesis
        _log("       judge + evidence synthesis (parallel)...")
        t_parallel = time.time()
        with ThreadPoolExecutor(max_workers=2) as pool:
            fut_judge = pool.submit(editor_judge, st)
            fut_synth = pool.submit(evidence_synthesizer, st)
            judge_out = fut_judge.result()
            synth_out = fut_synth.result()
        st = {**st, **judge_out, **synth_out}
        _log(f"       judge + synthesis wall {time.time()-t_parallel:.1f}s")
        
        # Elasticity
        step_t = time.time()
        st = {**st, **elasticity_evaluator(st)}
        _log(f"       elasticity {time.time()-step_t:.1f}s")
        
        _log(f"[5/6] chunk {i+1}/{len(chunks)} done ({time.time()-chunk_t0:.1f}s, total {time.time()-t0:.1f}s)")
        judgment = st.get("editor_judgment")
        elasticity = st.get("elasticity_result")
        if judgment:
            entry = build_chunk_judgment_entry(
                ch.id,
                i,
                judgment,
                elasticity,
                critic_result=st.get("critic_result"),
                defense_result=st.get("defense_result"),
                evidence_synthesis_result=st.get("evidence_synthesis_result"),
            )
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
                "evidence_synthesis_result": _dump(st["evidence_synthesis_result"]) if st.get("evidence_synthesis_result") else None,
                "character_database": _dump(st["character_database"]) if st.get("character_database") else None,
                "current_judgment": judgment.model_dump(),
            }
            on_chunk_done(run_id, ch.id, i, artifact, judgment, elasticity)

    state["document_state"] = doc_state

    # 6) Report
    _log(f"[6/6] building report...")
    state["run_id"] = run_id
    state["chunk_judgments"] = chunk_judgments
    state = {**state, **report_collector(state)}
    _log(f"[done] analysis complete ({time.time()-t0:.1f}s)")

    return state, chunk_judgments
