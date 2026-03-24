"""Re-run full pipeline for a single chunk in an existing run.

This script keeps existing chunking and run metadata, then recomputes one target
chunk with full stages (representation + detectors + critic/defense/judge).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import narrative_dag.llm as llm_runtime
from narrative_dag.db import init_db
from narrative_dag.nodes.character_map import character_map_builder
from narrative_dag.nodes.conflict import critic_agent, defense_agent
from narrative_dag.nodes.detection import run_all_detectors
from narrative_dag.nodes.ingestion import run_chunker, run_context_builder
from narrative_dag.nodes.judgment import build_chunk_judgment_entry, editor_judge, elasticity_evaluator
from narrative_dag.nodes.plot_overview import plot_overview_builder
from narrative_dag.nodes.representation import paragraph_analyzer, run_document_state_builder, voice_profiler
from narrative_dag.schemas import DocumentState, ElasticityResult, EditorJudgment, GenreIntention, RawDocument
from narrative_dag.store.judgment_store import JudgmentStore
from narrative_dag.store.run_store import RunStore


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Re-run one chunk in an existing run.")
    parser.add_argument("--db", default="artifacts/runtime.sqlite", help="SQLite DB path")
    parser.add_argument("--run-id", required=True, help="Target run_id")
    parser.add_argument("--chunk-id", required=True, help="Chunk ID (e.g., c10)")
    parser.add_argument("--genre", default="southern_gothic_horror", help="Genre label")
    parser.add_argument(
        "--input-file",
        default="tests/fixtures/golden_story_2.txt",
        help="Document source used for deterministic chunk reconstruction",
    )
    return parser.parse_args()


def dump_obj(x):
    if x is None:
        return None
    return x.model_dump() if hasattr(x, "model_dump") else x


def main() -> None:
    args = parse_args()
    text = Path(args.input_file).read_text(encoding="utf-8", errors="replace")

    conn = init_db(args.db)
    run_store = RunStore(conn)
    judgment_store = JudgmentStore(conn)
    cur = conn.cursor()

    # Build prior latest judgments for this run (used for prompt continuity).
    cur.execute(
        "select chunk_id, judgment_json from judgment_versions where run_id=? order by chunk_id, version",
        (args.run_id,),
    )
    latest: dict[str, dict] = {}
    for chunk_id, judgment_json in cur.fetchall():
        latest[chunk_id] = json.loads(judgment_json)

    chunk_judgments = []
    for chunk_id in sorted([c for c in latest if c != args.chunk_id], key=lambda x: int(x[1:])):
        judgment = EditorJudgment.model_validate(latest[chunk_id])
        chunk_judgments.append(
            build_chunk_judgment_entry(
                chunk_id,
                int(chunk_id[1:]) - 1,
                judgment,
                ElasticityResult(),
            )
        )

    llm = llm_runtime.get_llm()
    state = {
        "raw_document": RawDocument(text=text),
        "genre_intention": GenreIntention(genre=args.genre),
        "_llm": llm,
        "run_id": args.run_id,
        "chunk_judgments": chunk_judgments,
    }

    # Rebuild deterministic chunking + global context.
    state = {**state, **run_chunker(state)}
    chunks = state.get("chunks") or []
    if not any(c.id == args.chunk_id for c in chunks):
        raise RuntimeError(f"{args.chunk_id} not found in deterministic chunks.")

    state = {**state, **plot_overview_builder(state)}
    state["global_summary"] = state["plot_overview"].plot_summary if state.get("plot_overview") else ""
    state = {**state, **character_map_builder(state)}

    # Calibration from first chunk.
    state["current_chunk_id"] = chunks[0].id
    state = {**state, **run_context_builder(state)}
    state = {**state, **paragraph_analyzer(state)}
    state = {**state, **voice_profiler(state)}
    state = {**state, **run_document_state_builder(state)}
    doc_state = state.get("document_state") or DocumentState()

    # Replay preceding chunks through representation/doc-state only
    # so target chunk gets realistic rolling memory.
    for ch in chunks:
        if ch.id == args.chunk_id:
            break
        st = {
            "chunks": chunks,
            "current_chunk_id": ch.id,
            "global_summary": state.get("global_summary", ""),
            "genre_intention": state.get("genre_intention"),
            "document_state": doc_state,
            "character_database": state.get("character_database"),
            "chunk_judgments": chunk_judgments,
            "plot_overview": state.get("plot_overview"),
            "_llm": llm,
        }
        st = {**st, **run_context_builder(st)}
        st = {**st, **paragraph_analyzer(st)}
        st = {**st, **voice_profiler(st)}
        st = {**st, **run_document_state_builder(st)}
        doc_state = st.get("document_state") or doc_state

    # Full pipeline for target chunk.
    target = next(c for c in chunks if c.id == args.chunk_id)
    st = {
        "chunks": chunks,
        "current_chunk_id": target.id,
        "global_summary": state.get("global_summary", ""),
        "genre_intention": state.get("genre_intention"),
        "document_state": doc_state,
        "character_database": state.get("character_database"),
        "chunk_judgments": chunk_judgments,
        "plot_overview": state.get("plot_overview"),
        "_llm": llm,
    }
    for fn in [
        run_context_builder,
        paragraph_analyzer,
        voice_profiler,
        run_document_state_builder,
        run_all_detectors,
        critic_agent,
        defense_agent,
        editor_judge,
        elasticity_evaluator,
    ]:
        st = {**st, **(fn(st) or {})}

    judgment = st.get("editor_judgment")
    if judgment is None:
        raise RuntimeError("No editor judgment produced for target chunk.")

    version = judgment_store.save_judgment(
        args.run_id,
        args.chunk_id,
        judgment,
        source="editor_judge",
        rationale="",
    )

    artifact = {
        "target_chunk": target.model_dump(),
        "context_window": {
            "target_chunk": st["context_window"].target_chunk.model_dump(),
            "previous_chunks": [c.model_dump() for c in st["context_window"].previous_chunks],
            "next_chunks": [c.model_dump() for c in st["context_window"].next_chunks],
            "global_summary": getattr(st["context_window"], "global_summary", ""),
        },
        "detector_results": {
            "drift": dump_obj(st.get("drift_result")),
            "cliche": dump_obj(st.get("cliche_result")),
            "vagueness": dump_obj(st.get("vagueness_result")),
            "emotional_honesty": dump_obj(st.get("emotional_honesty_result")),
            "redundancy": dump_obj(st.get("redundancy_result")),
            "risk": dump_obj(st.get("risk_result")),
        },
        "critic_result": dump_obj(st.get("critic_result")),
        "defense_result": dump_obj(st.get("defense_result")),
        "character_database": dump_obj(st.get("character_database")),
        "current_judgment": judgment.model_dump(),
    }
    run_store.save_chunk_artifact(args.run_id, args.chunk_id, int(args.chunk_id[1:]) - 1, artifact)

    final_doc_state = st.get("document_state") or doc_state
    run_store.save_document_state(args.run_id, final_doc_state)

    print(f"run_id={args.run_id}")
    print(f"chunk_id={args.chunk_id}")
    print(f"version={version.version}")
    print(f"decision={judgment.decision}")
    print(f"severity={judgment.severity}")


if __name__ == "__main__":
    main()
