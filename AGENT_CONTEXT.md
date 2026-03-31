# Agent context: LangGraph narrative DAG (`editr`)

**Purpose.** This file is the handoff surface for future agents working on the narrative editorial pipeline. **Append** to the [Changelog (agents)](#changelog-agents) when you change graph topology, node contracts, or orchestration—do not rely on chat history.

**Product.** Advisory-only editorial analysis for long-form fiction: chunking, document state, detectors, critic/defense, per-chunk judgments, final report. Does **not** generate replacement prose.

---

## Critical: two orchestration paths

1. **Compiled LangGraph (per-chunk only)** — `build_chunk_pipeline_graph()` in `src/narrative_dag/graph.py`  
   - `StateGraph(dict)` with a linear chain ending at `END`.  
   - Used for visualization (`scripts/generate_graph_visuals.py`) and as the canonical **node order** for one chunk.  
   - **Not** invoked end-to-end for full-document runs today.

2. **Full run (`run_analysis`)** — same file, `run_analysis()`  
   - **Imperative** orchestration: LLM chunker → plot overview → character map → **calibration** on first chunk (runs context → paragraph → voice → `document_state_builder` once) → **for each chunk**, a Python loop that calls the **same node functions** in the same order as the compiled graph (plus `report_collector` at the end).  
   - If you add/remove/reorder pipeline steps, you must usually update **both** `build_chunk_pipeline_graph()` **and** the `steps` list inside `run_analysis()` (and calibration block if it duplicates the head of the pipeline).

**Chat / interaction** — `src/narrative_dag/nodes/interaction.py` exposes LangGraph-*style* node-shaped callables (`run_judge_explain`, `run_judge_reconsider`) but **there is no `StateGraph` for chat**; `NarrativeAnalysisService.chat()` wires LLM calls directly.

---

## LLM runtime: `RunLLMBundle` and per-run provider

- **`RunLLMBundle`** (`src/narrative_dag/llm.py`) — dataclass holding per-stage chat clients for one beta provider (`openai` or `gemini`): `llm`, `llm_detector`, `llm_judge`, `llm_quick_coach`, `llm_chat`. Built via `build_run_llm_bundle(provider)`.
- **Env default** — `LLM_PROVIDER` (and related `DEFAULT_LLM_PROVIDER_*` in `config.py`) selects the default backend; `resolve_run_llm_provider(requested)` maps API `provider` fields and coerces legacy `vertex` to `gemini` for bundles.
- **Per-request override** — Analyze / quick-coach / chat payloads may include `provider` when the service supports it; effective model IDs come from env (`OPENAI_*`, `GEMINI_*`) and stage-specific fast/pro routing inside `get_llm(...)`.
- **Public introspection** — `GET /v1/runtime/providers` returns configured flags and default model names (no secrets).

---

## HTTP API: static SPA and Docker

- **`EDITR_STATIC_DIR`** — When set to a directory containing `index.html`, FastAPI mounts static files **last** so `GET /health`, `/v1/*`, and WebSockets are unchanged; `StaticFiles(..., html=True)` enables SPA fallback for client routes.
- **Docker** — Root `Dockerfile`: Node stage builds `Editr-FrontEnd/dist`, Python stage `pip install .[api,mcp]`, copies `dist` → `/app/static`, sets `EDITR_STATIC_DIR` and `EDITR_DB_PATH`, runs `uvicorn narrative_dag.api.app:app` on `0.0.0.0:8000`.
- **MCP in containers** — `editr-mcp` is stdio-based; run with `docker run -i ... editr editr-mcp` or `docker exec -i <container> editr-mcp` so the client owns stdin/stdout.

---

## Per-chunk pipeline (compiled graph order)

| Order | Graph node name   | Function                     | Module                      |
|------:|-------------------|------------------------------|-----------------------------|
| 1     | `context_builder` | `run_context_builder`        | `nodes/ingestion.py`        |
| 2     | `paragraph_analyzer` | `paragraph_analyzer`      | `nodes/representation.py`   |
| 3     | `voice_profiler`  | `voice_profiler`             | `nodes/representation.py`   |
| 4     | `document_state_builder` | `run_document_state_builder` | `nodes/representation.py` |
| 5     | `detectors`       | `run_all_detectors`          | `nodes/detection.py`        |
| 6     | `critic`          | `critic_agent`               | `nodes/conflict.py`         |
| 7     | `defense`         | `defense_agent`              | `nodes/conflict.py`         |
| 8     | `editor_judge`    | `editor_judge`               | `nodes/judgment.py`         |
| 9     | `elasticity`      | `elasticity_evaluator`       | `nodes/judgment.py`         |

Prompts live under `src/narrative_dag/prompts/` (mirrors node domains).

---

## State contract

- **Authoritative schema:** `GraphState` (`TypedDict`, `total=False`) in `src/narrative_dag/schemas.py` — keys include `chunks`, `current_chunk_id`, `context_window`, `document_state`, detector `*_result`, `critic_result`, `defense_result`, `editor_judgment`, `elasticity_result`, `chunk_judgments`, `editorial_report`, plus `plot_overview`, `character_database`, `global_summary`, and injected `_llm` / `_llm_detector` / `_llm_judge`.  
- Runtime state is a **plain `dict`**; nodes return partial dicts merged by callers.

---

## Entry points

| Layer        | Location                         | Notes |
|-------------|-----------------------------------|-------|
| Service API | `src/narrative_dag/service.py`    | `NarrativeAnalysisService.analyze_document` → `run_analysis`; SQLite via `RunStore` / `JudgmentStore`. |
| CLI         | `src/narrative_dag/cli.py`        | `python -m narrative_dag.cli` |
| Graph build | `src/narrative_dag/graph.py`      | `build_chunk_pipeline_graph`, `run_analysis` |
| DAG diagrams | `scripts/generate_graph_visuals.py` | Writes `artifacts/graphs/` (Mermaid + optional PNG for chunk graph only). |

---

## Tests and invariants

- Graph / pipeline behavior: `tests/test_graph_e2e.py` and domain tests under `tests/test_*.py`.  
- Chunking contract (spans, chapter-first): summarized in `README.md`; ingestion logic in `nodes/ingestion.py`.

---

## Changelog (agents)

_Add a dated bullet when you change the DAG, node I/O, or orchestration._

- **2026-03-23** — Initial context file. Documented split between `build_chunk_pipeline_graph()` (compiled per-chunk DAG) and `run_analysis()` (full imperative orchestration with matching per-chunk loop). Noted absence of a compiled LangGraph for chat; interaction nodes are service-driven.
- **2026-03-23** — Persistent `EDITR_DB_PATH`, SCD2 `document_revisions` / `chunk_versions`, star-style `analytic_facts`, revision events, async jobs, FastAPI (`narrative_dag.api.app`), MCP (`mcp_server.py`), evidence spans + `evidence_fill`, `run_analysis(..., only_chunk_ids=...)` for incremental reruns, `build_incremental_chunk_graph()` alias.
- **2026-03-30** — Documented `RunLLMBundle`, env/API provider resolution, optional `EDITR_STATIC_DIR` SPA mount (after API routes), root multi-stage Docker image, and MCP stdio via `docker run -i` / `docker exec -i`.
