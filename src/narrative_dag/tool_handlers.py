"""Shared JSON tool handlers for MCP and OpenAI-style function calling."""

from __future__ import annotations

from typing import Any

from narrative_dag.contracts import AnalyzeDocumentRequest, ChatRequest
from narrative_dag.service import NarrativeAnalysisService


def analyze_document_tool(service: NarrativeAnalysisService, args: dict[str, Any]) -> dict[str, Any]:
    """Run full analysis; returns serialized AnalyzeDocumentResponse."""
    req = AnalyzeDocumentRequest.model_validate(args)
    resp = service.analyze_document(req)
    return resp.model_dump()


def judge_chat_tool(service: NarrativeAnalysisService, args: dict[str, Any]) -> dict[str, Any]:
    """Chunk-scoped chat; returns serialized ChatResponse."""
    req = ChatRequest.model_validate(args)
    resp = service.chat(req)
    return resp.model_dump()
