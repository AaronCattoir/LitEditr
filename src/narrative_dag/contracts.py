"""External request/response models for CLI, API, and future GUI."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from narrative_dag.schemas import EditorialReport, EditorJudgment, JudgmentVersion


class AnalyzeDocumentRequest(BaseModel):
    """Request to run full narrative analysis on a document."""

    document_text: str = Field(..., description="Raw document content")
    genre: str = Field(..., description="Primary genre label")
    subgenre_tags: list[str] = Field(default_factory=list)
    tone_descriptors: list[str] = Field(default_factory=list)
    reference_authors: list[str] = Field(default_factory=list)
    title: str | None = None
    author: str | None = None
    document_id: str | None = Field(default=None, description="Existing workspace document; creates one if omitted")
    revision_id: str | None = Field(
        default=None,
        description="Existing revision to attach lineage to; a new revision row is created from document_text if omitted",
    )


class AnalyzeDocumentResponse(BaseModel):
    """Response from full analysis run."""

    run_id: str
    report: EditorialReport
    success: bool = True
    error: str | None = None
    document_id: str | None = None
    revision_id: str | None = None


class ChatRequest(BaseModel):
    """Request to chat with the judge about a chunk (explain or reconsider)."""

    run_id: str
    chunk_id: str
    user_message: str
    mode: Literal["explain", "reconsider"] = Field(
        ...,
        description="explain = clarify reasoning only; reconsider = re-run editor_judge with full context",
    )


class ChatResponse(BaseModel):
    """Response from judge chat."""

    reply: str
    updated_judgment: EditorJudgment | None = None
    judgment_version: JudgmentVersion | None = None
    success: bool = True
    error: str | None = None
