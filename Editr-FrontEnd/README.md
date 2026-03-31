# Editr frontend

Vite + React editor UI. API calls go to the narrative DAG backend (`/v1/*`).

## Prerequisites

- Node.js 20+ (22 recommended)
- Backend running locally on port **8000** (see repo root `README.md`), or adjust the proxy below.

## Local development

```bash
cd Editr-FrontEnd
npm ci
npm run dev
```

Open the URL Vite prints (default `http://localhost:3000`). The dev server proxies `/v1` to `http://127.0.0.1:8000`.

To point the proxy elsewhere, edit `vite.config.ts` (`server.proxy['/v1'].target`).

## Production build

Run from the `Editr-FrontEnd` directory (repo root is one level up):

```bash
cd Editr-FrontEnd
npm ci
npm run build
```

Output is `dist/`. Serve it with the backend by setting `EDITR_STATIC_DIR` to the absolute path of `dist` (see root `README.md` / Docker image).

## Typecheck

```bash
npm run lint
```

LLM keys and provider choice live **only** on the server environment, not in the frontend bundle.
