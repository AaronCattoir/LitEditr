# editr

Advisory-only editorial analysis DAG for long-form narrative text (stories, novels). Ingests documents with user-defined genre intention, builds document state, runs detectors, performs critic/defense conflict, and delivers per-chunk editorial judgments (keep/cut/rewrite guidance) without generating replacement prose.

## Docker quickstart

Build and run API + built SPA on port 8000:

```bash
docker build -t editr .
docker run --rm -p 8000:8000 \
  -e OPENAI_API_KEY=... \
  -e GEMINI_API_KEY=... \
  -e LLM_PROVIDER=gemini \
  editr
```

Open `http://localhost:8000` for the UI; `GET /health` and `GET /v1/...` stay on the same process. SQLite lives at `/app/data/editr.sqlite` inside the container (add a volume if you want persistence).

Image defaults:

- `EDITR_STATIC_DIR=/app/static` (Vite `dist` copied at build time)
- `EDITR_DB_PATH=/app/data/editr.sqlite`

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
