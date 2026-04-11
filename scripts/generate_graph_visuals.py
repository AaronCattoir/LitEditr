"""Generate Mermaid DAG artifacts for documentation (static templates; mirrors `run_analysis` per-chunk steps)."""

from __future__ import annotations

from pathlib import Path

# Per-chunk pipeline: same node order as the loop in `narrative_dag.graph.run_analysis`.
# After `defense`, `editor_judge` and `evidence_synthesizer` run in parallel, then `elasticity`.
CHUNK_PIPELINE_MERMAID = """flowchart TD
    contextBuilder[context_builder] --> paragraphAnalyzer[paragraph_analyzer]
    paragraphAnalyzer --> voiceProfiler[voice_profiler]
    voiceProfiler --> documentStateBuilder[document_state_builder]
    documentStateBuilder --> detectors[run_all_detectors]
    detectors --> critic[critic_agent]
    critic --> defense[defense_agent]
    defense --> editorJudge[editor_judge]
    defense --> evidenceSynth[evidence_synthesizer]
    editorJudge --> elasticity[elasticity_evaluator]
    evidenceSynth --> elasticity
"""


def main() -> None:
    out_dir = Path("artifacts/graphs")
    out_dir.mkdir(parents=True, exist_ok=True)

    chunk_mermaid = CHUNK_PIPELINE_MERMAID.strip() + "\n"

    (out_dir / "chunk_pipeline.mmd").write_text(chunk_mermaid, encoding="utf-8")

    (out_dir / "chunk_pipeline.md").write_text(
        "# Chunk Pipeline (per chunk)\n\n```mermaid\n" + chunk_mermaid + "```\n",
        encoding="utf-8",
    )

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
    defense --> evidenceSynth[evidence_synthesizer]
    editorJudge --> elasticity[elasticity_evaluator]
    evidenceSynth --> elasticity
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
