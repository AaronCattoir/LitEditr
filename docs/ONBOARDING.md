# Editr onboarding (Docker, environment, verification)

This guide assumes you run Editr in **Docker** with the API and built web UI on port **8000**. For architecture and context systems, see [wiki README](wiki/README.md).

## Prerequisites

- **Docker** (Docker Desktop on Windows is fine)
- **Git** (to clone from GitHub)
- API access to **OpenAI** and/or **Google AI (Gemini)** depending on your chosen provider

## Secrets workflow

1. Copy [.env.example](../.env.example) to `.env` in the project root (same folder as `docker-compose.yml`).
2. Fill in at least the variables in [Required variables for LLM](#required-variables-for-llm).
3. **Never commit `.env`** — it is listed in `.gitignore`. Keys are **server-side only**; the web UI does not read them from the browser.

## Required variables for LLM

The runtime checks keys before calling the model (see `is_openai_configured` / `is_gemini_configured` in `src/narrative_dag/llm.py`).

| Setting | Values / notes |
| --- | --- |
| `LLM_PROVIDER` | `openai` or `gemini` (default in code: `gemini`) |
| OpenAI | Set `OPENAI_API_KEY` when `LLM_PROVIDER=openai` |
| Gemini | Set `GEMINI_API_KEY` **or** `GOOGLE_API_KEY` when `LLM_PROVIDER=gemini` |

## Optional model IDs and tuning

See comments in `.env.example` for `OPENAI_MODEL`, `GEMINI_MODEL`, fast/pro tiers, `LLM_TEMPERATURE`, Quick Coach bounds, Inkblot memory, and related flags. Defaults are defined in `src/narrative_dag/config.py`.

## Paths: local development vs Docker

- **Bare-metal / local Python**: `.env.example` sets `EDITR_DB_PATH=editr.sqlite` (file in the current working directory unless you override).
- **Docker image** ([Dockerfile](../Dockerfile)): defaults include `EDITR_DB_PATH=/app/data/editr.sqlite` and `EDITR_STATIC_DIR=/app/static` (the built SPA copied into the image).
- **docker compose** ([docker-compose.yml](../docker-compose.yml)): bind-mounts host `.\data` to `/app/data`. Compose does **not** override `EDITR_DB_PATH`, so the image default keeps the database **on the volume**.

**Footgun:** If you run `docker run ... --env-file .env` using a `.env` that still has `EDITR_DB_PATH=editr.sqlite`, SQLite may be created under `/app` **outside** the mounted `data` folder, so data will not persist where you expect. For Docker with the `./data` volume, either **remove** `EDITR_DB_PATH` from the env file you pass into the container, or set `EDITR_DB_PATH=/app/data/editr.sqlite` explicitly.

Pet soul / Inkblot seed content: the image includes `docs/pet`. Override with `EDITR_PET_SOUL_DIR` if you mount a custom directory.

## Run the container

### PowerShell (Windows)

| Method | Command | Persistence |
| --- | --- | --- |
| **Compose (recommended)** | `New-Item -ItemType Directory -Force data` then `docker compose up --build` (from repo root) | Host folder `.\data` → `/app/data` |
| **Plain Docker** | `docker build -t editr .` then `docker run --rm -p 8000:8000 -v "${PWD}\data:/app/data"` plus `-e` / `--env-file` for API keys | Same bind mount |

Ensure `.env` exists beside `docker-compose.yml` so Compose can substitute variables such as `GEMINI_API_KEY`.

### Linux / macOS / Git Bash

Same flow; use `mkdir -p data` and, for plain Docker, `-v "$(pwd)/data:/app/data"` (or equivalent).

### Downloadable image from a website

If you distribute a **saved image tarball** (not from a registry):

**Publish (example):**

```powershell
docker build -t editr .
docker save -o D:\artifacts\editr-image.tar editr
```

**User import:**

```powershell
docker load -i .\editr-image.tar
```

Then run with the same env and volume as above, for example:

```powershell
docker run --rm -p 8000:8000 -v "${PWD}\data:/app/data" --env-file .env editr
```

(Adjust paths and options to match how you ship keys.)

## Verify configuration

### Checklist

- [ ] `LLM_PROVIDER` is `openai` or `gemini` as intended.
- [ ] For **gemini**: `GEMINI_API_KEY` or `GOOGLE_API_KEY` is non-empty.
- [ ] For **openai**: `OPENAI_API_KEY` is non-empty.
- [ ] For Compose: `.env` is next to `docker-compose.yml`.
- [ ] For Docker with a data volume: you did not leave a bare-metal `EDITR_DB_PATH=editr.sqlite` in an `--env-file` unless you understand where the file will be created.

### Optional script

From the repo root (with dev dependencies installed, or `python-dotenv` available):

```powershell
python scripts/check_env.py
python scripts/check_env.py --docker
```

`--docker` warns when `EDITR_DB_PATH` looks like a relative host path that can break volume persistence.

### Smoke tests

**Health (PowerShell):**

```powershell
curl.exe -sf http://localhost:8000/health/ready
```

Or:

```powershell
Invoke-RestMethod http://localhost:8000/health/ready
```

You should see JSON including `"status":"ready"` when the app and SQLite are up.

**UI:** Open `http://localhost:8000`, create or open a document, save, and run **Analyze** (requires valid LLM keys).

## MCP in Docker (optional)

The image includes the MCP server (`editr-mcp`). It uses **stdio**, not HTTP—intended for tools such as Cursor.

```powershell
docker run --rm -i `
  -e OPENAI_API_KEY=... `
  -e GEMINI_API_KEY=... `
  -e LLM_PROVIDER=gemini `
  editr `
  editr-mcp
```

Use `-i` so stdio stays attached. You can also `docker exec -i <container> editr-mcp` on a running container with the same environment.

## GitHub vs downloadable container

- **From GitHub:** clone the repo, configure `.env`, and use `docker compose up --build` (or build/run as above).
- **From a website tarball:** `docker load` the provided `.tar`, then run with the same env and volume guidance; no container registry required.
