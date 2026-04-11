"""Model routing, provider config, genre profiles, and thresholds."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Literal

from dotenv import load_dotenv

DialecticDepth = Literal["off", "review", "deep"]

load_dotenv()

# Persistent SQLite path for CLI, MCP, and API (avoid :memory: for cross-request chat).
DEFAULT_DB_PATH = os.getenv("EDITR_DB_PATH", "editr.sqlite")


@dataclass
class GenreProfile:
    """Thresholds and allowed variance by genre."""

    genre: str
    drift_sensitivity: float = 0.5  # 0=lenient, 1=strict
    cliche_tolerance: float = 0.5
    vagueness_impact_weights: dict[str, float] = field(default_factory=lambda: {"low": 0.3, "medium": 0.6, "high": 1.0})
    extra: dict[str, Any] = field(default_factory=dict)


# Default calibration chunk count for document_state_builder
DEFAULT_CALIBRATION_CHUNKS = 5

# Context window: chunks before/after target
DEFAULT_CONTEXT_WINDOW_SIZE = 3

# LLM defaults (provider can be swapped without changing node code).
# Beta runtime path supports openai + gemini only; vertex remains available via legacy get_llm without a bundle.
DEFAULT_LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini")
DEFAULT_LLM_PROVIDER_DEFAULT_STAGE = os.getenv(
    "LLM_PROVIDER_DEFAULT_STAGE", DEFAULT_LLM_PROVIDER
)
DEFAULT_LLM_PROVIDER_DETECTOR = os.getenv(
    "LLM_PROVIDER_DETECTOR", DEFAULT_LLM_PROVIDER
)
DEFAULT_LLM_PROVIDER_JUDGMENT = os.getenv(
    "LLM_PROVIDER_JUDGMENT", DEFAULT_LLM_PROVIDER
)
DEFAULT_LLM_PROVIDER_CONFLICT = os.getenv(
    "LLM_PROVIDER_CONFLICT", DEFAULT_LLM_PROVIDER
)
DEFAULT_LLM_PROVIDER_QUICK_COACH = os.getenv(
    "LLM_PROVIDER_QUICK_COACH", DEFAULT_LLM_PROVIDER
)
DEFAULT_LLM_PROVIDER_CHAT = os.getenv("LLM_PROVIDER_CHAT", DEFAULT_LLM_PROVIDER)
DEFAULT_GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
DEFAULT_VERTEX_MODEL = os.getenv("VERTEX_MODEL", "gemini-3.1-pro-preview")
DEFAULT_OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4-mini")
DEFAULT_LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0"))

# Optional stage-specific model routing.
# Detectors can use cheaper/faster models while conflict/judgment stays on a stronger model.
DEFAULT_GEMINI_FAST_MODEL = os.getenv("GEMINI_FAST_MODEL", "gemini-2.5-flash")
DEFAULT_GEMINI_PRO_MODEL = os.getenv("GEMINI_PRO_MODEL", "gemini-3.1-pro")
DEFAULT_VERTEX_FAST_MODEL = os.getenv("VERTEX_FAST_MODEL", "gemini-3.1-flash")
DEFAULT_VERTEX_PRO_MODEL = os.getenv("VERTEX_PRO_MODEL", DEFAULT_VERTEX_MODEL)
DEFAULT_OPENAI_FAST_MODEL = os.getenv("OPENAI_FAST_MODEL", "gpt-5.4-mini")
DEFAULT_OPENAI_PRO_MODEL = os.getenv("OPENAI_PRO_MODEL", "gpt-5.4")
# Per-request LLM timeout (seconds) to prevent indefinite stalls.
DEFAULT_LLM_TIMEOUT_S = float(os.getenv("LLM_TIMEOUT_S", "90"))

# Quick coach: block when |len(current) - len(analyzed)| exceeds this derived cap
QUICK_COACH_OOB_RATIO = float(os.getenv("QUICK_COACH_OOB_RATIO", "0.3"))
QUICK_COACH_OOB_MIN_CHARS = int(os.getenv("QUICK_COACH_OOB_MIN_CHARS", "120"))
QUICK_COACH_OOB_MAX_CHARS = int(os.getenv("QUICK_COACH_OOB_MAX_CHARS", "1200"))

# Story persona (inkblot): first materialization thresholds
PERSONA_MIN_ANALYZED_WORDS = int(os.getenv("PERSONA_MIN_ANALYZED_WORDS", "1200"))
PERSONA_MIN_ANALYZED_CHUNKS = int(os.getenv("PERSONA_MIN_ANALYZED_CHUNKS", "3"))
PERSONA_PARTIAL_REFRESH_MIN_WORD_DELTA = int(os.getenv("PERSONA_PARTIAL_REFRESH_MIN_WORD_DELTA", "300"))

# Story chat explicit context
STORY_CHAT_MAX_WORDS_DEFAULT = int(os.getenv("STORY_CHAT_MAX_WORDS_DEFAULT", "5000"))
STORY_CHAT_ACTIVE_TURNS = int(os.getenv("STORY_CHAT_ACTIVE_TURNS", "20"))

# Inkblot document memory: batch merge every N real (non–quick-coach) user turns
INKBLOT_MEMORY_BATCH_USER_TURNS = int(os.getenv("INKBLOT_MEMORY_BATCH_USER_TURNS", "5"))
# Persona paragraph digest: schedule on same cadence (debounced async job)
INKBLOT_PERSONA_DIGEST_USER_TURNS = int(os.getenv("INKBLOT_PERSONA_DIGEST_USER_TURNS", "5"))
# Max transcript chars for close-summary / batch prompts (truncate deterministically)
INKBLOT_MEMORY_TRANSCRIPT_MAX_CHARS = int(os.getenv("INKBLOT_MEMORY_TRANSCRIPT_MAX_CHARS", "48000"))

# Chunking / context safety
CHUNKER_MAX_ONE_SHOT_CHARS = int(os.getenv("CHUNKER_MAX_ONE_SHOT_CHARS", "12000"))
# If an individual detected chapter is still too large, fall back to deterministic chunk_document.
CHAPTER_DETECTION_MAX_CHARS = int(os.getenv("CHAPTER_DETECTION_MAX_CHARS", "20000"))

# Built-in genre profiles (can be extended)
GENRE_PROFILES: dict[str, GenreProfile] = {
    "literary_fiction": GenreProfile(genre="literary_fiction", drift_sensitivity=0.4, cliche_tolerance=0.3),
    "thriller": GenreProfile(genre="thriller", drift_sensitivity=0.6, cliche_tolerance=0.6),
    "sci_fi": GenreProfile(genre="sci_fi", drift_sensitivity=0.5, cliche_tolerance=0.5),
    "memoir": GenreProfile(genre="memoir", drift_sensitivity=0.5, cliche_tolerance=0.5),
}


def get_genre_profile(genre: str) -> GenreProfile:
    """Return profile for genre; default if unknown."""
    key = genre.lower().replace(" ", "_").replace("-", "_")
    return GENRE_PROFILES.get(key, GenreProfile(genre=key))


def get_default_dialectic_depth() -> DialecticDepth:
    """Internal pipeline: extra mediator/synthesis LLM steps before editor_judge (latency vs depth)."""
    raw = (os.getenv("EDITR_DIALECTIC_DEPTH", "off") or "off").strip().lower()
    if raw in ("off", "review", "deep"):
        return raw  # type: ignore[return-value]
    return "off"
