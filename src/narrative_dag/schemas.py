"""Pydantic models and state contracts for the narrative analysis DAG."""

from __future__ import annotations

from typing import Any, Literal, TypedDict

from pydantic import BaseModel, Field


# --- Top-level inputs ---


class GenreIntention(BaseModel):
    """User-supplied genre/style intention for consistency checks."""

    genre: str = Field(..., description="Primary genre label (e.g. literary fiction, thriller)")
    subgenre_tags: list[str] = Field(default_factory=list)
    tone_descriptors: list[str] = Field(default_factory=list)
    reference_authors: list[str] = Field(default_factory=list)
    short_story_single_chapter: bool = Field(
        default=False,
        description="True when the work is a single-chapter short story; relax multi-chapter arc expectations",
    )


class RawDocument(BaseModel):
    """Raw document input."""

    text: str
    title: str | None = None
    author: str | None = None
    chapter_markers: list[str] | None = None


# --- Ingestion / representation ---


class Chunk(BaseModel):
    """Deterministic, referenceable unit (paragraph-level)."""

    id: str = Field(..., description="Stable id e.g. c1, c2")
    text: str
    position: int
    # Character offsets (0-based, end exclusive) into the original RawDocument.text used for chunking.
    start_char: int
    end_char: int


class ChunkBoundary(BaseModel):
    """Narrative-beat boundary as a character span (end exclusive)."""

    start_char: int
    end_char: int
    beat_label: str = ""


class ChunkBoundaries(BaseModel):
    """Structured response model for LLM chunk boundary detection."""

    boundaries: list[ChunkBoundary] = Field(default_factory=list)


class ContextWindow(BaseModel):
    """Local + global context for a target chunk."""

    target_chunk: Chunk
    previous_chunks: list[Chunk] = Field(default_factory=list)
    next_chunks: list[Chunk] = Field(default_factory=list)
    global_summary: str = ""


class PromptContext(BaseModel):
    """Normalized prompt-facing context bundle for editorial stages."""

    target_chunk: Chunk
    previous_chunks: list[Chunk] = Field(default_factory=list)
    next_chunks: list[Chunk] = Field(default_factory=list)
    global_summary: str = ""
    plot_summary: str = ""
    story_point: str = ""
    stakes: str = ""
    theme_hypotheses: list[str] = Field(default_factory=list)
    emotional_curve: list[dict[str, Any]] = Field(default_factory=list)
    narrative_map: list[dict[str, Any]] = Field(default_factory=list)
    character_voice_map: dict[str, Any] = Field(default_factory=dict)
    character_database: list[dict[str, Any]] = Field(default_factory=list)
    prior_chunk_judgments: list[dict[str, Any]] = Field(default_factory=list)
    genre_intention: GenreIntention | None = None


class VoiceSignals(BaseModel):
    """Qualitative voice signals from paragraph analysis."""

    # Vertex structured output rejects nullable string fields in schema anyOf.
    formality: str = ""
    distance: str = ""
    rhythm: str = ""
    extra: dict[str, Any] = Field(default_factory=dict)


class ParagraphAnalysis(BaseModel):
    """Per-chunk analysis from paragraph_analyzer."""

    function: str = Field(..., description="Narrative function of the chunk")
    intent: str = Field(..., description="Authorial intent")
    voice_signals: VoiceSignals = Field(default_factory=VoiceSignals)
    emotional_register: str = ""
    weakness: str = ""


class VoiceLayer(BaseModel):
    """One axis of voice — fixed shape for LLM structured output (no open-ended dicts)."""

    summary: str = Field(
        default="",
        description="2–4 sentences grounded in the target passage; empty if truly not applicable",
    )
    observations: list[str] = Field(
        default_factory=list,
        description="Short evidence-backed notes (e.g. diction, cadence); max ~8 items",
    )


class VoiceProfile(BaseModel):
    """Structured voice features (lexical, syntactic, rhetorical, psychological)."""

    lexical: VoiceLayer = Field(default_factory=VoiceLayer)
    syntactic: VoiceLayer = Field(default_factory=VoiceLayer)
    rhetorical: VoiceLayer = Field(default_factory=VoiceLayer)
    psychological: VoiceLayer = Field(default_factory=VoiceLayer)


class DialogueAnalysis(BaseModel):
    """Optional: character voice consistency."""

    speaker: str = ""
    style_features: dict[str, Any] = Field(default_factory=dict)
    distinctiveness_score: float = 0.0


class AllowedVariance(BaseModel):
    """Per-feature min/max bounds for drift detection."""

    bounds: dict[str, dict[str, float]] = Field(
        default_factory=dict,
        description="e.g. {'formality': {'min': 0.2, 'max': 0.8}}",
    )


class ArcMapEntry(BaseModel):
    """One beat in the narrative arc.

    OpenAI structured outputs reject ``list[dict[str, Any]]`` (items must declare
    fixed properties with additionalProperties: false). Use explicit fields here.
    """

    phase: str = Field(
        default="",
        description="Beat label, e.g. setup, inciting incident, rising action, climax, resolution",
    )
    summary: str = Field(default="", description="What happens in this phase")


class PlotOverview(BaseModel):
    """Global plot summary for editor context (story point, arc, stakes)."""

    plot_summary: str = Field(default="", description="Short global synopsis")
    story_point: str = Field(default="", description="What the story is fundamentally about")
    arc_map: list[ArcMapEntry] = Field(
        default_factory=list,
        description="Beginning/middle/end, turning points",
    )
    stakes: str = Field(default="", description="What matters if protagonist fails")
    theme_hypotheses: list[str] = Field(default_factory=list, description="Optional theme hypotheses")


class CharacterEntry(BaseModel):
    """Canonical character identity with aliases and role."""

    canonical_name: str = ""
    aliases: list[str] = Field(default_factory=list)
    role: str = ""
    notes: str = ""


class CharacterDatabase(BaseModel):
    """Document-level cast map used to stabilize references."""

    characters: list[CharacterEntry] = Field(default_factory=list)


class DocumentState(BaseModel):
    """Global editor memory: voice baseline, emotional curve, narrative map, etc."""

    voice_baseline: VoiceProfile | dict[str, Any] = Field(default_factory=dict)
    emotional_curve: list[dict[str, Any]] = Field(default_factory=list)
    narrative_map: list[dict[str, Any]] = Field(default_factory=list)
    character_voice_map: dict[str, Any] = Field(default_factory=dict)
    allowed_variance: AllowedVariance = Field(default_factory=AllowedVariance)
    genre_intention: GenreIntention | None = None
    plot_overview: PlotOverview | None = None
    character_database: CharacterDatabase | None = None


# --- Detection layer outputs ---


class DriftResult(BaseModel):
    drift_score: float = 0.0
    drift_type: Literal["tone", "syntax", "psychological", ""] = ""
    evidence: str = ""
    confidence: float = 0.0


class ClicheResult(BaseModel):
    cliche_flags: list[str] = Field(default_factory=list)
    severity: float = 0.0


class VaguenessResult(BaseModel):
    vague_phrases: list[str] = Field(default_factory=list)
    impact: Literal["low", "medium", "high"] = "low"


class EmotionalHonestyResult(BaseModel):
    mismatch: bool = False
    expected_emotion: str = ""
    actual_text_signal: str = ""


class RedundancyResult(BaseModel):
    redundant_with: list[str] = Field(default_factory=list, description="Chunk ids e.g. c3, c7")
    type: Literal["idea", "phrasing"] = "idea"


class RiskResult(BaseModel):
    risk_type: Literal["none", "stylistic", "emotional", "intellectual"] = "none"
    payoff: Literal["working", "failing"] = "working"


# --- Evidence spans (UI highlights; absolute offsets in revision text) ---


class EvidenceSpan(BaseModel):
    """Character offsets into the document revision text (0-based, end exclusive)."""

    start_char: int = Field(..., ge=0)
    end_char: int = Field(..., ge=0)
    quote: str = ""
    label: str = ""


# --- Conflict layer ---


class CriticResult(BaseModel):
    critique: str = ""
    failure_points: list[str] = Field(default_factory=list)
    verdict: Literal["fail", "weak", "borderline"] = "borderline"
    evidence_spans: list[EvidenceSpan] = Field(default_factory=list)


class DefenseResult(BaseModel):
    defense: str = ""
    valid_points: list[str] = Field(default_factory=list)
    salvageability: Literal["high", "medium", "low"] = "medium"
    evidence_spans: list[EvidenceSpan] = Field(default_factory=list)


# --- Judgment layer ---


class EditorJudgment(BaseModel):
    """Advisory only; no generated prose."""

    decision: Literal["keep", "cut", "rewrite"] = "keep"
    severity: float = 0.0
    reasoning: str = ""
    core_issue: str = ""
    guidance: str = ""
    is_drift: bool = False
    evidence_spans: list[EvidenceSpan] = Field(default_factory=list)


class ElasticityResult(BaseModel):
    is_intentional_deviation: bool = False
    justification: str = ""
    override_drift: bool = False


# --- Report & versioning ---


class ChunkJudgmentEntry(BaseModel):
    """Single chunk's judgment in the report."""

    chunk_id: str
    position: int
    judgment: EditorJudgment
    elasticity: ElasticityResult | None = None
    critic_result: CriticResult | None = None
    defense_result: DefenseResult | None = None


class EditorialReport(BaseModel):
    """Final per-chunk judgments + document-level summary."""

    run_id: str = ""
    chunk_judgments: list[ChunkJudgmentEntry] = Field(default_factory=list)
    document_summary: str = ""


class JudgmentVersion(BaseModel):
    """Immutable audit record for a judgment."""

    chunk_id: str
    run_id: str
    version: int
    judgment: EditorJudgment
    source: Literal["editor_judge", "judge_reconsideration"] = "editor_judge"
    rationale_for_change: str = ""


class ContextBundle(BaseModel):
    """Assembled from RunStore+JudgmentStore for interaction; never from chat history."""

    target_chunk: Chunk
    context_window: ContextWindow
    document_state: DocumentState
    detector_results: dict[str, Any] = Field(default_factory=dict)
    critic_result: CriticResult | None = None
    defense_result: DefenseResult | None = None
    current_judgment: EditorJudgment | None = None
    genre_intention: GenreIntention | None = None


class QuickCoachAdvice(BaseModel):
    """Short structured tip from the sparkle quick-coach path (no full pipeline)."""

    headline: str = ""
    bullets: list[str] = Field(default_factory=list, max_length=8)
    try_next: str | None = None


class ChatTurn(BaseModel):
    """Stored for UX continuity only; not used as model grounding."""

    role: Literal["user", "assistant"]
    content: str
    chunk_id: str = ""
    run_id: str = ""
    judgment_version: int | None = None


# --- Graph state (TypedDict for LangGraph) ---


class GraphState(TypedDict, total=False):
    """Top-level state keyed by chunk_id with global doc-level cache."""

    run_id: str
    genre_intention: GenreIntention
    raw_document: RawDocument
    chunks: list[Chunk]
    plot_overview: PlotOverview | None
    character_database: CharacterDatabase | None
    global_summary: str
    current_chunk_id: str
    context_window: ContextWindow
    prompt_context: PromptContext
    paragraph_analysis: ParagraphAnalysis
    voice_profile: VoiceProfile
    dialogue_analysis: DialogueAnalysis | None
    document_state: DocumentState
    drift_result: DriftResult | None
    cliche_result: ClicheResult | None
    vagueness_result: VaguenessResult | None
    emotional_honesty_result: EmotionalHonestyResult | None
    redundancy_result: RedundancyResult | None
    risk_result: RiskResult | None
    critic_result: CriticResult | None
    defense_result: DefenseResult | None
    editor_judgment: EditorJudgment | None
    elasticity_result: ElasticityResult | None
    chunk_judgments: list[ChunkJudgmentEntry]
    editorial_report: EditorialReport | None
