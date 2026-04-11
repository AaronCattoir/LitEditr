# editr

Advisory-only editorial analysis DAG for long-form narrative text (stories, novels). Ingests documents with user-defined genre intention, builds document state, runs detectors, performs critic/defense conflict, and delivers per-chunk editorial judgments (keep/cut/rewrite guidance) without generating replacement prose.

**Internal context wiki:** [docs/wiki/README.md](docs/wiki/README.md) (how pipeline, Inkblot, bundles, and client state fit together, with worked examples).

## Docker quickstart

Full setup (PowerShell-first Docker commands, `.env` reference, verification checklist, and optional `docker save` / `docker load` for a website-hosted image): [docs/ONBOARDING.md](docs/ONBOARDING.md).

Build and run API + built SPA on port 8000:

```bash
docker build -t editr .
docker run --rm -p 8000:8000 \
  -e OPENAI_API_KEY=... \
  -e GEMINI_API_KEY=... \
  -e LLM_PROVIDER=gemini \
  editr
```

Open `http://localhost:8000` for the UI; `GET /health` (liveness), `GET /health/ready` (SQLite ping), and `GET /v1/...` stay on the same process. SQLite lives at `/app/data/editr.sqlite` inside the container (use a volume for persistence).

Image defaults:

- `EDITR_STATIC_DIR=/app/static` (Vite `dist` copied at build time)
- `EDITR_DB_PATH=/app/data/editr.sqlite`
- Pet soul / Inkblot seed markdown: `docs/pet` is copied into the image; override with `EDITR_PET_SOUL_DIR` if you mount custom content.

### Local beta: compose + persistence

```bash
mkdir -p data
docker compose up --build
```

This bind-mounts `./data` → `/app/data` so the database survives container restarts. Copy `.env.example` to `.env` and set API keys (see table below). Optional: restrict the port to this machine only:

```bash
docker run --rm -p 127.0.0.1:8000:8000 -v "$(pwd)/data:/app/data" -e LLM_PROVIDER=gemini -e GEMINI_API_KEY=... editr
```

**First-run smoke (with keys set):** open the UI → create or open a document → save → run analyze. `curl -sf http://localhost:8000/health/ready` should return `{"status":"ready"}`.

## Provider environment (OpenAI / Gemini)

The beta runtime uses **openai** or **gemini** only. Set one primary toggle and the matching API key(s):

| Variable | Role |
|----------|------|
| `LLM_PROVIDER` | `openai` or `gemini` (default in code: `gemini`) |
| `OPENAI_API_KEY` | Required when using OpenAI |
| `GEMINI_API_KEY` or `GOOGLE_API_KEY` | Required when using Gemini direct API |
| `OPENAI_MODEL`, `GEMINI_MODEL`, etc. | Model IDs (see `.env.example`) |

Copy `.env.example` to `.env` and fill keys locally. Optional: `EDITR_STATIC_DIR` pointing at a `dist` folder to serve the SPA alongside the API.

## MCP in Docker (optional)

The image installs `.[api,mcp]`. The MCP server speaks stdio and is intended for tools (e.g. Cursor), not HTTP:

```bash
docker run --rm -i \
  -e OPENAI_API_KEY=... \
  -e GEMINI_API_KEY=... \
  -e LLM_PROVIDER=gemini \
  editr \
  editr-mcp
```

Use `-i` (interactive) so stdio stays attached; configure your client to launch this command (or `docker exec -i <container> editr-mcp` against a running container with the same env).

## Local setup (without Docker)

```bash
pip install -e ".[dev,api,mcp]"
```

### HTTP API (FastAPI)

```bash
editr-api
# or: python -m narrative_dag.api
# or (listen on all interfaces): python -m uvicorn narrative_dag.api.app:app --host 0.0.0.0 --port 8000
```

### MCP (stdio)

```bash
editr-mcp
```

### Frontend

See [Editr-FrontEnd/README.md](Editr-FrontEnd/README.md).

## Architecture

- **Ingestion** → **Representation** → **Detection** → **Conflict** → **Judgment** → **Interaction**
- SQLite for runs, judgments, chat turns; optional Parquet export for analytics.
- CLI first; service layer is transport-agnostic for future GUI/API.

## Chunking contract

- The ingestion step uses an LLM to split the input text into narrative-beat chunks.
- Chunk boundaries are **character spans** over the original text (`start_char` inclusive, `end_char` exclusive).
- Chunks form a **contiguous partition** (no overlaps, no gaps).
- Very long inputs use a **chapter-first** strategy, then stitch global offsets.

## License

MIT — see [LICENSE](LICENSE).
