"""Contract tests: service request/response and chat API."""

from __future__ import annotations

import pytest
from narrative_dag.service import NarrativeAnalysisService
from narrative_dag.contracts import AnalyzeDocumentRequest, ChatRequest


def test_analyze_document_contract(temp_db_path):
    service = NarrativeAnalysisService(db_path=temp_db_path)
    request = AnalyzeDocumentRequest(
        document_text="First.\n\nSecond.\n\nThird.",
        genre="literary_fiction",
    )
    response = service.analyze_document(request)
    assert response.success
    assert response.run_id
    assert response.document_id
    assert response.revision_id
    assert response.report.run_id == response.run_id
    assert len(response.report.chunk_judgments) == 3
    service.close()


def test_chat_after_analyze(temp_db_path):
    service = NarrativeAnalysisService(db_path=temp_db_path)
    req = AnalyzeDocumentRequest(document_text="One.\n\nTwo.", genre="literary_fiction")
    resp = service.analyze_document(req)
    assert resp.success
    chat_req = ChatRequest(run_id=resp.run_id, chunk_id="c1", user_message="Why?", mode="explain")
    chat_resp = service.chat(chat_req)
    assert chat_resp.success
    assert chat_resp.reply
    service.close()
