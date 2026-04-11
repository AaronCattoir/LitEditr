# Agent context: narrative DAG (`editr`)

**Purpose.** This file is the handoff surface for future agents working on the narrative editorial pipeline. **Append** to the [Changelog (agents)](#changelog-agents) when you change graph topology, node contracts, or orchestration—do not rely on chat history.

**Product.** Advisory-only editorial analysis for long-form fiction: chunking, document state, detectors, critic/defense, per-chunk judgments, final report. Does **not** generate replacement prose.

---

## Orchestration: `run_analysis` only

**Full run (`run_analysis`)** — `src/narrative_dag/graph.py`  
- **Imperative** orchestration: LLM chunker → plot overview + character map (parallel) → **calibration** on first chunk (runs context → paragraph → voice → `document_state_builder` once) → **for each chunk**, a Python loop over the node functions below (then `report_collector` after all chunks).  
- **Mermaid diagrams** for docs live in `scripts/generate_graph_visuals.py` (writes `artifacts/graphs/`). Keep them in sync when you change the per-chunk loop or calibration block.

**Chat / interaction** — `src/narrative_dag/nodes/interaction.py` exposes node-shaped callables (`run_judge_explain`, `run_judge_reconsider`); `NarrativeAnalysisService.chat()` wires LLM calls directly (no separate graph library).

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

## Per-chunk pipeline (order in `run_analysis` loop)

| Order | Step name            | Function                     | Module                      |
|------:|----------------------|------------------------------|-----------------------------|
| 1     | `context_builder`    | `run_context_builder`        | `nodes/ingestion.py`        |
| 2     | `paragraph_analyzer` | `paragraph_analyzer`       | `nodes/representation.py`   |
| 3     | `voice_profiler`     | `voice_profiler`             | `nodes/representation.py`   |
| 4     | `document_state_builder` | `run_document_state_builder` | `nodes/representation.py` |
| 5     | `detectors`          | `run_all_detectors`          | `nodes/detection.py`        |
| 6     | `critic`             | `critic_agent`               | `nodes/conflict.py`         |
| 7     | `defense`            | `defense_agent`              | `nodes/conflict.py`         |
| 8a/b  | (parallel)         | `editor_judge` **and** `evidence_synthesizer` | `nodes/judgment.py` |
| 9     | `elasticity`         | `elasticity_evaluator`       | `nodes/judgment.py`         |

Prompts live under `src/narrative_dag/prompts/` (mirrors node domains).

---

## State contract

- Runtime pipeline state is a **plain `dict[str, Any]`** merged across steps. Typical keys include `chunks`, `current_chunk_id`, `context_window`, `document_state`, detector `*_result`, `critic_result`, `defense_result`, `editor_judgment`, `evidence_synthesis_result`, `elasticity_result`, `chunk_judgments`, `editorial_report`, plus `plot_overview`, `character_database`, `global_summary`, and injected `_llm` / `_llm_detector` / `_llm_judge`. Pydantic models in `schemas.py` describe persisted/API shapes; the in-memory dict is not a single `TypedDict`.

---

## Entry points

| Layer        | Location                         | Notes |
|-------------|-----------------------------------|-------|
| Service API | `src/narrative_dag/service.py`    | `NarrativeAnalysisService.analyze_document` → `run_analysis`; SQLite via `RunStore` / `JudgmentStore`. |
| CLI         | `src/narrative_dag/cli.py`        | `editr-cli` (console script) or `python -m narrative_dag.cli` |
| Graph / analysis | `src/narrative_dag/graph.py` | `run_analysis` |
| DAG diagrams | `scripts/generate_graph_visuals.py` | Writes `artifacts/graphs/` (static Mermaid). |

---

## Tests and invariants

- Graph / pipeline behavior: `tests/test_graph_e2e.py` and domain tests under `tests/test_*.py`.  
- Chunking contract (spans, chapter-first): summarized in `README.md`; ingestion logic in `nodes/ingestion.py`.

---

## Changelog (agents)

_Add a dated bullet when you change the DAG, node I/O, or orchestration._

- **2026-04-10** — Dead-code cleanup: removed LangGraph dependency and `build_chunk_pipeline_graph` / `build_incremental_chunk_graph`; per-chunk topology documented via static Mermaid in `scripts/generate_graph_visuals.py`. Removed unused `GraphState` / `ChatTurn` schema types, unused `store/repositories.py`, and test-only diff helpers (production keeps `sha256_text` only). Added `editr-cli` console script.
- **2026-04-01** — Inkblot: SQLite tables `story_persona_snapshots`, `story_persona_events`, `story_chat_sessions`, `story_chat_turns`; optional `async_jobs.input_hash` / `output_persona_version`. Pet soul markdown at `docs/pet/PET_SOUL.md`. APIs: `GET /v1/documents/{document_id}/persona`, `POST /v1/documents/{document_id}/story-chat`, session/turn listing. Full analyze schedules `persona_refresh` async (disable with `EDITR_DISABLE_PERSONA_REFRESH=1`).
- **2026-04-01** — Frontend: lower-left Inkblot launcher (`MessageCircle`), `StoryChatPanel` sliding from the left; `storyChatStorage` persists `session_id` per document; first open POSTs starter `user_message` for greeting, then `listStoryChatTurns` on reopen. Hidden when `VITE_USE_MOCK_API` or no `documentId`/chapter.
- **2026-04-02** — Inkblot visuals: `InkblotPersonaLLMSnapshot` now includes optional `visual_model` (`svg_path_d`, `primary_color`, `secondary_color`, `animation_speed`). `persona_refresh` prompt asks LLM to return avatar-safe SVG path + palette. Frontend parses `llm_snapshot.visual_model` and renders animated `InkblotAvatar` in launcher and story chat header; polls persona while `persona_refresh_pending`.
- **2026-03-23** — Initial context file. Documented compiled per-chunk LangGraph (`build_chunk_pipeline_graph`) vs `run_analysis()` imperative orchestration; interaction nodes are service-driven. *(Superseded 2026-04-10: LangGraph builders removed.)*
- **2026-03-23** — Persistent `EDITR_DB_PATH`, SCD2 `document_revisions` / `chunk_versions`, star-style `analytic_facts`, revision events, async jobs, FastAPI (`narrative_dag.api.app`), MCP (`mcp_server.py`), evidence spans + `evidence_fill`, `run_analysis(..., only_chunk_ids=...)` for incremental reruns.
- **2026-03-30** — Documented `RunLLMBundle`, env/API provider resolution, optional `EDITR_STATIC_DIR` SPA mount (after API routes), root multi-stage Docker image, and MCP stdio via `docker run -i` / `docker exec -i`.
