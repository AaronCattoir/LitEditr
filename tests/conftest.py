"""Pytest fixtures and config."""

from __future__ import annotations

import tempfile
from pathlib import Path
import re

import pytest
from langchain_core.messages import AIMessage


class _StructuredInvoker:
    def __init__(self, schema):
        self.schema = schema

    def invoke(self, _messages):
        name = self.schema.__name__
        message_text = ""
        if _messages:
            first = _messages[0]
            message_text = getattr(first, "content", "") if hasattr(first, "content") else str(first)
        payload_map = {
            "PlotOverview": {
                "plot_summary": "A protagonist faces escalating pressure and reaches a decisive turn.",
                "story_point": "A person must choose integrity over comfort.",
                "arc_map": [{"phase": "setup"}, {"phase": "turn"}, {"phase": "resolution"}],
                "stakes": "If they fail, they lose their core relationship.",
                "theme_hypotheses": ["integrity", "sacrifice"],
            },
            "ParagraphAnalysis": {
                "function": "narration",
                "intent": "advance_plot",
                "voice_signals": {"formality": "neutral", "distance": "close", "rhythm": "mixed", "extra": {}},
                "emotional_register": "tense",
                "weakness": "",
            },
            "VoiceProfile": {
                "lexical": {"sentence_length_avg": 15},
                "syntactic": {"complexity": 0.6},
                "rhetorical": {"emphasis": "moderate"},
                "psychological": {"distance": "close"},
            },
            "DialogueAnalysis": {"speaker": "", "style_features": {}, "distinctiveness_score": 0.6},
            "DriftResult": {"drift_score": 0.2, "drift_type": "tone", "evidence": "minor shift", "confidence": 0.7},
            "ClicheResult": {"cliche_flags": [], "severity": 0.0},
            "VaguenessResult": {"vague_phrases": [], "impact": "low"},
            "EmotionalHonestyResult": {"mismatch": False, "expected_emotion": "tension", "actual_text_signal": "tension"},
            "RedundancyResult": {"redundant_with": [], "type": "idea"},
            "RiskResult": {"risk_type": "stylistic", "payoff": "working"},
            "CriticResult": {"critique": "Some compression issues.", "failure_points": ["compression"], "verdict": "weak"},
            "DefenseResult": {"defense": "Compression supports pacing.", "valid_points": ["pacing"], "salvageability": "high"},
            "EditorJudgment": {
                "decision": "rewrite",
                "severity": 0.5,
                "reasoning": "Needs sharper execution but core intent is viable.",
                "core_issue": "compression",
                "guidance": "Tighten transitions and specificity.",
                "is_drift": False,
            },
            "ElasticityResult": {
                "is_intentional_deviation": False,
                "justification": "Deviation is not strongly intentional.",
                "override_drift": False,
            },
            "CharacterDatabase": {
                "characters": [
                    {
                        "canonical_name": "Lanky",
                        "aliases": ["Monkey McGee", "Lanky Kong"],
                        "role": "protagonist",
                        "notes": "Tower climber; grief-driven narrative center.",
                    },
                    {
                        "canonical_name": "Wayne",
                        "aliases": [],
                        "role": "coworker",
                        "notes": "Spotter/coworker in tower scenes.",
                    },
                ]
            },
        }
        payload = payload_map.get(name)
        if name == "ChunkBoundaries":
            # Extract the raw DOCUMENT from the prompt.
            # The ingestion prompt uses:
            #   <<<TEXT>>>
            #   ...document...
            #   <<<ENDTEXT>>>
            m = re.search(r"<<<TEXT>>>\s*(.*?)\s*<<<ENDTEXT>>>", message_text, flags=re.DOTALL)
            doc = m.group(1) if m else ""

            # Partition deterministically by paragraph blocks (blank-line separated),
            # but expressed as global character spans with end-exclusive offsets.
            starts: list[int] = [0]
            if doc:
                sep_re = re.compile(r"(?:\r?\n)\s*(?:\r?\n)+")
                for s_m in sep_re.finditer(doc):
                    i = s_m.end()
                    while i < len(doc) and doc[i].isspace():
                        i += 1
                    if i < len(doc):
                        starts.append(i)
            starts = sorted(set(starts))
            if 0 not in starts:
                starts = [0] + starts
            if len(doc) not in starts:
                starts.append(len(doc))
            starts = sorted(set(starts))
            boundaries = []
            for i in range(len(starts) - 1):
                s = starts[i]
                e = starts[i + 1]
                if e > s:
                    boundaries.append({"start_char": s, "end_char": e, "beat_label": "beat"})
            payload = {"boundaries": boundaries}
        if payload is None:
            payload = {}
        return self.schema.model_validate(payload)


class FakeLLM:
    def with_structured_output(self, schema):
        return _StructuredInvoker(schema)

    def invoke(self, _messages):
        return AIMessage(content="Judgment rationale based on full context.")


@pytest.fixture(autouse=True)
def mock_llm(monkeypatch):
    import narrative_dag.llm as llm_runtime

    monkeypatch.setattr(llm_runtime, "get_llm", lambda *args, **kwargs: FakeLLM())


@pytest.fixture
def sample_document():
    """Short sample for chunking and analysis."""
    return """First paragraph. It sets the scene.

Second paragraph. Something happens here.

Third has a bit more. At the end of the day we need clarity.

Fourth wraps up. Needless to say, it ends."""


@pytest.fixture
def genre_intention():
    from narrative_dag.schemas import GenreIntention
    return GenreIntention(genre="literary_fiction", subgenre_tags=[], tone_descriptors=[], reference_authors=[])


@pytest.fixture
def temp_db_path():
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        path = f.name
    yield path
    Path(path).unlink(missing_ok=True)
