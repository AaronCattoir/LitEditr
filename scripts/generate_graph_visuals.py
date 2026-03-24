"""Generate visual DAG artifacts from LangGraph definitions."""

from __future__ import annotations

from pathlib import Path

from narrative_dag.graph import build_chunk_pipeline_graph


def main() -> None:
    out_dir = Path("artifacts/graphs")
    out_dir.mkdir(parents=True, exist_ok=True)

    chunk_graph = build_chunk_pipeline_graph().get_graph()
    chunk_mermaid = chunk_graph.draw_mermaid()

    # Raw Mermaid
    (out_dir / "chunk_pipeline.mmd").write_text(chunk_mermaid, encoding="utf-8")

    # Markdown preview
    (out_dir / "chunk_pipeline.md").write_text(
        "# Chunk Pipeline DAG\n\n```mermaid\n" + chunk_mermaid + "\n```\n",
        encoding="utf-8",
    )

    # Optional PNG if renderer is available.
    try:
        png = chunk_graph.draw_mermaid_png()
        (out_dir / "chunk_pipeline.png").write_bytes(png)
    except Exception:
        pass

    # Full workflow (top-level orchestration in run_analysis).
    full_mermaid = """flowchart TD
    rawDoc[RawDocument] --> chunker[llm_char_chunker]
    genreIntent[GenreIntention] --> documentStateBuilder[document_state_builder]
    chunker --> plotOverview[plot_overview_builder]
    plotOverview --> globalSummary[global_summary]
    globalSummary --> calibration[calibration_pass_first_chunk]
    calibration --> loop[for_each_chunk]
    loop --> contextBuilder[context_builder]
    contextBuilder --> paragraphAnalyzer[paragraph_analyzer]
    paragraphAnalyzer --> voiceProfiler[voice_profiler]
    voiceProfiler --> documentStateBuilder
    documentStateBuilder --> detectors[run_all_detectors]
    detectors --> critic[critic_agent]
    critic --> defense[defense_agent]
    defense --> editorJudge[editor_judge]
    editorJudge --> elasticity[elasticity_evaluator]
    elasticity --> collect[append_chunk_judgment]
    collect --> loop
    loop --> reportCollector[report_collector]
    reportCollector --> editorialReport[EditorialReport]
"""
    (out_dir / "full_workflow.mmd").write_text(full_mermaid, encoding="utf-8")
    (out_dir / "full_workflow.md").write_text(
        "# Full Workflow DAG\n\n```mermaid\n" + full_mermaid + "\n```\n",
        encoding="utf-8",
    )

    print(f"Wrote graph artifacts to {out_dir.resolve()}")


if __name__ == "__main__":
    main()
