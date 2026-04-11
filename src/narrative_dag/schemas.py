"""Pydantic models and state contracts for the narrative analysis DAG."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


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
    drift_type: Literal["tone", "syntax", "psychological", "narrative", ""] = ""
    evidence: str = ""
    confidence: float = 0.0

    @field_validator("drift_type", mode="before")
    @classmethod
    def normalize_drift_type(cls, v: Any) -> str:
        """Map model paraphrases (e.g. 'narrative architecture') onto allowed literals."""
        if v is None or v == "":
            return ""
        s = str(v).strip().lower().replace("-", " ").replace("_", " ")
        if s in ("tone", "syntax", "psychological", "narrative"):
            return s
        if "narrative" in s or "scene" in s and "architecture" in s:
            return "narrative"
        if "psychological" in s or (s.startswith("psych") and "syntax" not in s):
            return "psychological"
        if "syntax" in s:
            return "syntax"
        if "tone" in s:
            return "tone"
        return ""


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


class SpanSynthesis(BaseModel):
    quote: str = Field(..., description="The exact verbatim text span from the chunk.")
    critic_blurb: str = Field(..., description="One short, plain language sentence synthesizing the critic's point.")
    advocate_blurb: str = Field(..., description="One short, plain language sentence synthesizing the advocate/defense point.")
    start_char: int = 0
    end_char: int = 0


class EvidenceSynthesisResult(BaseModel):
    spans: list[SpanSynthesis] = Field(default_factory=list)


# --- Conflict layer ---


class CriticResult(BaseModel):
    critique: str = ""
    failure_points: list[str] = Field(default_factory=list)
    verdict: Literal["fail", "weak", "borderline"] = "borderline"
    evidence_spans: list[EvidenceSpan] = Field(default_factory=list)

    @field_validator("verdict", mode="before")
    @classmethod
    def normalize_verdict(cls, v: Any) -> str:
        if v is None:
            return "borderline"
        s = str(v).strip().lower().replace("_", " ").replace("-", " ")
        if s in {"fail", "weak", "borderline"}:
            return s
        # Prompt currently uses "working"; keep schema stable and coerce to nearest
        # existing bucket so we do not raise validation errors in production runs.
        if s in {"working", "works", "pass", "ok", "good"}:
            return "borderline"
        if "fail" in s or "broken" in s:
            return "fail"
        if "weak" in s or "undersell" in s:
            return "weak"
        return "borderline"


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
    evidence_synthesis: EvidenceSynthesisResult | None = None


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


class InkblotVisualModel(BaseModel):
    """Generative SVG hints for the Inkblot companion avatar (viewBox 0 0 100 100)."""

    svg_path_d: str = Field(
        default="",
        description="Single SVG path d attribute only; closed symmetric inkblot-like shape inside 0–100 coords",
    )
    primary_color: str = Field(
        default="#6B5B6B",
        description="Fill or main ink color as #RRGGBB",
    )
    secondary_color: str = Field(
        default="#C4A8B8",
        description="Accent or highlight as #RRGGBB",
    )
    animation_speed: float = Field(
        default=1.0,
        ge=0.25,
        le=3.0,
        description="Relative motion speed; >1 tenser/faster, <1 calmer/slower",
    )


class InkblotPersonaLLMSnapshot(BaseModel):
    """LLM-compressed persona layer; advisory only."""

    one_liner: str = Field(default="", description="How the pet relates to this story in one line")
    alignment_notes: str = Field(default="", description="What the pet should emphasize for this writer")
    personality_paragraph: str = Field(
        default="",
        description="2–3 sentences: Inkblot's voice/presence for this story (advisory; does not override safety)",
        max_length=2000,
    )
    tone_reminders: list[str] = Field(default_factory=list, max_length=8)
    visual_model: InkblotVisualModel | None = Field(
        default=None,
        description="Optional abstract inkblot SVG path + palette for UI avatar",
    )


class InkblotPersonaParagraphRefresh(BaseModel):
    """Partial LLM output when only refreshing personality_paragraph (digest job)."""

    personality_paragraph: str = Field(default="", max_length=2000)


class InkblotMemoryMergeResult(BaseModel):
    """Incremental batch merge over a segment of story chat (every N inkblot user turns)."""

    schema_version: int = Field(default=1, ge=1)
    rolling_summary: str = Field(default="", max_length=4000)
    open_goals: list[str] = Field(default_factory=list, max_length=12)
    noted_emotions: list[str] = Field(default_factory=list, max_length=12)


class InkblotMemoryCloseSummary(BaseModel):
    """Full-session extraction when the user closes the chat panel."""

    schema_version: int = Field(default=1, ge=1)
    session_point: str = Field(default="", max_length=2000)
    session_goals: list[str] = Field(default_factory=list, max_length=12)
    session_emotions: list[str] = Field(default_factory=list, max_length=12)
