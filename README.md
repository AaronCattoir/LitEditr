# editr

Advisory-only editorial analysis DAG for long-form narrative text (stories, novels). Ingests documents with user-defined genre intention, builds document state, runs detectors, performs critic/defense conflict, and delivers per-chunk editorial judgments (keep/cut/rewrite guidance) without generating replacement prose.

## Setup

```bash
pip install -e ".[dev]"
```

For the HTTP API and MCP server:

```bash
pip install -e ".[dev,api,mcp]"
```

## Run

```bash
python -m narrative_dag.cli --help
```

### HTTP API (FastAPI)

```bash
editr-api
# or: python -m narrative_dag.api
```

Default DB path: `EDITR_DB_PATH` (falls back to `editr.sqlite`). Endpoints include `GET /health`, `POST /v1/documents`, `POST /v1/documents/{id}/revisions`, `POST /v1/revisions/{revision_id}/analyze` (202 + job), `GET /v1/jobs/{job_id}`, `GET /v1/runs`, `GET /v1/revisions/{id}/chunks`, `POST /v1/chat`.

### MCP (stdio)

```bash
editr-mcp
```

### Environment

- `EDITR_DB_PATH` — SQLite file for runs, SCD2 revisions, jobs, and analytic facts (default `editr.sqlite`).
- `MEM0_API_KEY` — optional; when set and `mem0` is installed, analysis summaries can sync to Mem0.

## Architecture

- **Ingestion** → **Representation** → **Detection** → **Conflict** → **Judgment** → **Interaction**
- SQLite for runs, judgments, chat turns; optional Parquet export for analytics.
- CLI first; service layer is transport-agnostic for future GUI/API.

## Chunking Contract

- The ingestion step uses an LLM to split the input text into narrative-beat chunks.
- Chunk boundaries are represented as **character spans** over the original `RawDocument.text`:
  - `Chunk.start_char` (0-based, inclusive)
  - `Chunk.end_char` (0-based, end-exclusive)
- The produced chunks form a **contiguous partition** of the document (no overlaps, no gaps).
- For very long inputs (novel-sized), chunking switches to a **chapter-first** strategy:
  - detect `Chapter`/`Part` spans
  - run one-shot chunking per chapter
  - stitch chapter-local spans back into **global** `start_char`/`end_char` offsets.
