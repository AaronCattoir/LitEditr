"""MCP stdio server exposing analyze_document and judge_chat tools."""

from __future__ import annotations

import json
import os
import sys

from narrative_dag.config import DEFAULT_DB_PATH
from narrative_dag.service import NarrativeAnalysisService
from narrative_dag.tool_handlers import analyze_document_tool, judge_chat_tool


def main() -> None:
    os.environ.setdefault("EDITR_DB_PATH", DEFAULT_DB_PATH if DEFAULT_DB_PATH != ":memory:" else "editr.sqlite")
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as e:
        print("Install MCP extras: pip install editr[mcp]", file=sys.stderr)
        raise SystemExit(1) from e

    service = NarrativeAnalysisService()

    mcp = FastMCP("editr")

    @mcp.tool()
    def analyze_document(
        document_text: str,
        genre: str,
        subgenre_tags: list[str] | None = None,
        tone_descriptors: list[str] | None = None,
        reference_authors: list[str] | None = None,
        title: str | None = None,
        author: str | None = None,
        document_id: str | None = None,
        revision_id: str | None = None,
    ) -> str:
        """Run full narrative analysis. Uses persistent SQLite (EDITR_DB_PATH)."""
        args = {
            "document_text": document_text,
            "genre": genre,
            "subgenre_tags": subgenre_tags or [],
            "tone_descriptors": tone_descriptors or [],
            "reference_authors": reference_authors or [],
            "title": title,
            "author": author,
            "document_id": document_id,
            "revision_id": revision_id,
        }
        return json.dumps(analyze_document_tool(service, args), default=str)

    @mcp.tool()
    def judge_chat(
        run_id: str,
        chunk_id: str,
        user_message: str,
        mode: str = "explain",
    ) -> str:
        """Explain or reconsider judgment for a chunk (requires prior analyze run_id)."""
        args = {
            "run_id": run_id,
            "chunk_id": chunk_id,
            "user_message": user_message,
            "mode": mode,
        }
        return json.dumps(judge_chat_tool(service, args), default=str)

    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
