"""HTTP API package (FastAPI)."""

from __future__ import annotations


def main() -> None:
    import uvicorn

    uvicorn.run(
        "narrative_dag.api.app:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
    )
