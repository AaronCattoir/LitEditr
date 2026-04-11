# Multi-stage: build Editr-FrontEnd, then Python API + MCP extras with static SPA at /app/static.

FROM node:22-alpine AS frontend
WORKDIR /fe
COPY Editr-FrontEnd/package.json Editr-FrontEnd/package-lock.json ./
RUN npm ci
COPY Editr-FrontEnd/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app

ENV EDITR_STATIC_DIR=/app/static \
    EDITR_DB_PATH=/app/data/editr.sqlite \
    PYTHONUNBUFFERED=1

RUN mkdir -p /app/data /app/static

COPY pyproject.toml README.md ./
COPY src ./src
# Inkblot / pet soul defaults to repo-root docs/pet (see EDITR_PET_SOUL_DIR)
COPY docs/pet ./docs/pet
RUN pip install --no-cache-dir ".[api,mcp]"

COPY --from=frontend /fe/dist/ /app/static/

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "narrative_dag.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
