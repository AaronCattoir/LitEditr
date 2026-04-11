"""External request/response models for CLI, API, and future GUI."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

DialecticDepthLiteral = Literal["off", "review", "deep"]

from narrative_dag.schemas import EditorialReport, EditorJudgment, JudgmentVersion, QuickCoachAdvice


class ClientChunkSpan(BaseModel):
    """Chunk boundary over document_text: start/end are **Unicode code point** indices (Python 3 `str`), end exclusive."""

    chunk_id: str = Field(..., description="Stable id e.g. c1, must be unique in this request")
    start_char: int = Field(..., ge=0)
    end_char: int = Field(..., ge=0)


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
    chunks: list[ClientChunkSpan] | None = Field(
        default=None,
        description="If set and non-empty, skip internal chunker and use these spans (must partition document_text)",
    )
    base_run_id: str | None = Field(
        default=None,
        description="When only_chunk_ids is set, copy non-target artifacts from this run into the new run",
    )
    only_chunk_ids: list[str] | None = Field(
        default=None,
        description="If set and non-empty with base_run_id, re-run pipeline only for these chunk ids; merge the rest",
    )
    short_story_single_chapter: bool = Field(
        default=False,
        description="Editor flag: single-chapter short story (prompts relax novel-style arc expectations)",
    )
    provider: Literal["openai", "gemini"] | None = Field(
        default=None,
        description="LLM backend for this run (openai or gemini); defaults from server config",
    )
    dialectic_depth: DialecticDepthLiteral | None = Field(
        default=None,
        description="Optional: override EDITR_DIALECTIC_DEPTH (off | review | deep). Internal; not shown in UI.",
    )

    @model_validator(mode="after")
    def _partial_analyze_pair(self) -> AnalyzeDocumentRequest:
        oc = self.only_chunk_ids or []
        if oc and not self.base_run_id:
            raise ValueError("base_run_id is required when only_chunk_ids is non-empty")
        if self.base_run_id and not oc:
            raise ValueError("only_chunk_ids must be non-empty when base_run_id is set")
        if oc:
            if not self.chunks:
                raise ValueError("chunks are required for partial analysis")
            known = {c.chunk_id for c in self.chunks}
            for cid in oc:
                if cid not in known:
                    raise ValueError(f"only_chunk_ids references unknown chunk_id: {cid}")
        return self


class AnalyzeDocumentResponse(BaseModel):
    """Response from full analysis run."""

    run_id: str
    report: EditorialReport
    success: bool = True
    error: str | None = None
    document_id: str | None = None
    revision_id: str | None = None
    analysis_kind: str | None = Field(default=None, description="full or partial")


class ChatRequest(BaseModel):
    """Request to chat with the judge about a chunk (explain or reconsider)."""

    run_id: str
    chunk_id: str
    user_message: str
    provider: Literal["openai", "gemini"] | None = Field(
        default=None,
        description="LLM backend for this chat turn; defaults from server config",
    )
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


class QuickCoachRequest(BaseModel):
    """Sparkle: one section, brief coach note. Optional fields are forwarded when auto-queueing full analyze."""

    chunk_id: str = Field(..., description="Chunk business id for this section")
    focus: str | None = Field(default=None, description="Optional user intent or question")
    run_id: str | None = Field(default=None, description="Pin a specific analysis run; must belong to this revision")
    genre: str | None = None
    subgenre_tags: list[str] = Field(default_factory=list)
    tone_descriptors: list[str] = Field(default_factory=list)
    reference_authors: list[str] = Field(default_factory=list)
    title: str | None = None
    author: str | None = None
    current_chunk_text: str | None = Field(
        default=None,
        description="Manuscript slice for this chunk as in the editor; enables diff vs last analysis and OOB checks",
    )
    chunks: list[ClientChunkSpan] | None = Field(
        default=None,
        description="Optional current revision chunk spans; enables partial quick-coach fallback queueing",
    )
    short_story_single_chapter: bool = Field(
        default=False,
        description="Editor flag: single-chapter short story (passed through to quick-coach prompt)",
    )
    provider: Literal["openai", "gemini"] | None = Field(
        default=None,
        description="LLM backend for quick coach (and analyze jobs queued from sparkle)",
    )
    story_chat_session_id: str | None = Field(
        default=None,
        description="Existing Inkblot story-chat session to append turns to; omit to create a new session",
    )
    append_story_chat: bool = Field(
        default=False,
        description="When true, persist quick-coach result as user+assistant story-chat turns",
    )


class QuickCoachResponse(BaseModel):
    """Result of quick coach (200) or error detail for API mapping."""

    advice: QuickCoachAdvice | None = None
    run_id: str | None = None
    revision_id: str | None = None
    success: bool = True
    error: str | None = None
    error_code: str | None = None
    requires_reanalysis: bool = False
    delta_chars: int | None = None
    threshold_chars: int | None = None
    analyzed_char_len: int | None = None
    current_char_len: int | None = None
    story_chat_session_id: str | None = None
    story_chat_appended: bool = False


class StoryChatRequest(BaseModel):
    """Inkblot story chat: explicit chunks or chapter slice; no RAG."""

    revision_id: str | None = Field(
        default=None,
        description="Manuscript revision to read chunks from; defaults to document current revision",
    )
    user_message: str = Field(..., min_length=1)
    chunk_ids: list[str] | None = Field(default=None, description="If set, hydrate these chunk texts in order")
    chapter_id: str | None = Field(default=None, description="When chunk_ids empty, use this chapter slice")
    max_words: int = Field(default=5000, ge=100, le=50_000)
    session_id: str | None = Field(default=None, description="Continue an existing story chat session")
    provider: Literal["openai", "gemini"] | None = None


class StoryChatResponse(BaseModel):
    answer: str = ""
    used_persona_version: int | None = None
    session_id: str = ""
    context_manifest: dict[str, Any] = Field(default_factory=dict)
    truncation_notice: str | None = None
    confidence: float | None = None
    persona_refresh_pending: bool = False
    inkblot_memory_updated_at: str | None = None
    success: bool = True
    error: str | None = None
    error_code: str | None = None
    recovery_hints: list[str] = Field(default_factory=list)


class StoryPersonaResponse(BaseModel):
    """Latest inkblot persona for a document."""

    document_id: str
    snapshot: dict[str, Any] | None = None
    soul_loaded: bool = False
    soul_paths: list[str] = Field(default_factory=list)
    persona_refresh_pending: bool = False
    latest_run_id: str | None = Field(default=None, description="Run used for story-wide context when available")
    inkblot_memory: dict[str, Any] | None = Field(
        default=None,
        description="Document-scoped writer memory (goals, emotions, session summaries)",
    )
    inkblot_memory_updated_at: str | None = None


class StoryChatSessionCloseRequest(BaseModel):
    """Optional body when finalizing a session (panel close)."""

    provider: Literal["openai", "gemini"] | None = None
    last_turn_index: int | None = Field(
        default=None,
        description="Highest turn_index included in the close summary; omit for all turns",
    )


class StoryChatSessionCloseResponse(BaseModel):
    success: bool = True
    scheduled: bool = False
    error: str | None = None
