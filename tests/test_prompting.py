"""Tests for prompt policy and prompt-context assembly."""

from __future__ import annotations

from narrative_dag.prompt_context import build_prompt_context
from narrative_dag.nodes.quick_coach import slim_narrative_text_from_bundle
from narrative_dag.prompts.conflict import critic_prompt
from narrative_dag.prompts.detection import detector_prompt
from narrative_dag.prompts.interaction import explain_prompt, reconsider_prompt
from narrative_dag.prompts.judgment import editor_judgment_prompt
from narrative_dag.prompts.quick_coach import quick_coach_prompt
from narrative_dag.prompts.representation import paragraph_analysis_prompt
from narrative_dag.schemas import (
    Chunk,
    ChunkJudgmentEntry,
    ContextBundle,
    ContextWindow,
    CriticResult,
    DocumentState,
    EditorJudgment,
    ElasticityResult,
    GenreIntention,
    PlotOverview,
)


def _make_chunk(chunk_id: str, text: str, position: int) -> Chunk:
    return Chunk(id=chunk_id, text=text, position=position, start_char=0, end_char=len(text))


def test_build_prompt_context_includes_style_metadata_and_recent_judgments():
    target = _make_chunk("c2", "I heard her breathing in the wire.", 1)
    prev = _make_chunk("c1", "The tower swayed in the rain.", 0)
    nxt = _make_chunk("c3", "Wayne laughed too long at nothing.", 2)
    genre = GenreIntention(
        genre="southern_gothic_horror",
        subgenre_tags=["working_class", "psychological"],
        tone_descriptors=["humid", "oppressive"],
        reference_authors=["Harry Crews"],
    )
    state = {
        "context_window": ContextWindow(
            target_chunk=target,
            previous_chunks=[prev],
            next_chunks=[nxt],
            global_summary="A lineman mistakes grief for a haunting.",
        ),
        "document_state": DocumentState(
            emotional_curve=[{"chunk_id": "c1", "register": "uneasy"}],
            narrative_map=[{"chunk_id": "c1", "intent": "foreshadow"}],
            character_voice_map={"Wayne": {"register": "loose"}},
            character_database={
                "characters": [
                    {
                        "canonical_name": "Lanky",
                        "aliases": ["Lanky Kong"],
                        "role": "protagonist",
                        "notes": "Main POV narrator.",
                    }
                ]
            },
            genre_intention=genre,
            plot_overview=PlotOverview(
                plot_summary="A lineman spirals after hearing a dead line breathe.",
                story_point="Grief becomes a trap masquerading as connection.",
                stakes="He may surrender himself to delusion.",
                theme_hypotheses=["grief", "self-destruction"],
            ),
        ),
        "genre_intention": genre,
        "chunk_judgments": [
            ChunkJudgmentEntry(
                chunk_id="c1",
                position=0,
                judgment=EditorJudgment(decision="rewrite", guidance="Sharpen the dread."),
                elasticity=ElasticityResult(),
            )
        ],
    }

    prompt_ctx = build_prompt_context(state)

    assert prompt_ctx is not None
    assert prompt_ctx.story_point == "Grief becomes a trap masquerading as connection."
    assert prompt_ctx.genre_intention is not None
    assert prompt_ctx.genre_intention.reference_authors == ["Harry Crews"]
    assert prompt_ctx.character_database[0]["canonical_name"] == "Lanky"
    assert prompt_ctx.prior_chunk_judgments[0]["chunk_id"] == "c1"


def test_representation_prompt_includes_editorial_policy_and_genre_metadata():
    genre = GenreIntention(
        genre="literary_fiction",
        subgenre_tags=["first_person"],
        tone_descriptors=["wry"],
        reference_authors=["Denis Johnson"],
    )
    prompt_ctx = build_prompt_context(
        {
            "context_window": ContextWindow(
                target_chunk=_make_chunk("c1", "At the end of the day, I kept climbing.", 0),
                previous_chunks=[],
                next_chunks=[],
                global_summary="A man keeps moving after the wrong sound reaches him.",
            ),
            "genre_intention": genre,
            "document_state": DocumentState(
                genre_intention=genre,
                plot_overview=PlotOverview(
                    plot_summary="A lineman mistakes grief for a call back from the dead.",
                    story_point="He wants connection badly enough to trust a haunting.",
                ),
            ),
        }
    )

    prompt = paragraph_analysis_prompt(prompt_ctx)

    assert "EDITORIAL POLICY" in prompt
    assert "Distinguish narrator voice" in prompt
    assert "Subgenre tags: first_person" in prompt
    assert "Reference authors: Denis Johnson" in prompt


def test_detector_prompt_has_detector_specific_guardrails():
    prompt_ctx = build_prompt_context(
        {
            "context_window": ContextWindow(
                target_chunk=_make_chunk("c1", "Bad coffee and worse weather.", 0),
                previous_chunks=[],
                next_chunks=[],
                global_summary="A lineman drifts deeper into his grief.",
            ),
            "genre_intention": GenreIntention(genre="southern_gothic_horror"),
            "document_state": DocumentState(),
        }
    )

    prompt = detector_prompt("cliche", prompt_ctx, paragraph_intent="build dread")

    assert "the cliche detector" in prompt
    assert "Do not punish colloquial voice" in prompt
    assert "Paragraph intent: build dread" in prompt


def test_judgment_prompt_includes_preservation_tie_breaks():
    prompt_ctx = build_prompt_context(
        {
            "context_window": ContextWindow(
                target_chunk=_make_chunk("c1", "I reached for the phone again.", 0),
                previous_chunks=[],
                next_chunks=[],
                global_summary="A grieving man keeps answering a dead line.",
            ),
            "genre_intention": GenreIntention(genre="southern_gothic_horror"),
            "document_state": DocumentState(),
        }
    )

    prompt = editor_judgment_prompt(
        prompt_ctx,
        "drift_result: {'drift_score': 0.2}",
        '{"critique":"too broad"}',
        '{"defense":"the voice is intentional"}',
    )

    assert "PROSE-CRAFT" in prompt and "NARRATIVE ARCHITECTURE" in prompt
    assert "SEVERITY SCALE" in prompt
    assert "Weigh the defense's argument" in prompt


def test_interaction_prompts_reuse_editorial_policy():
    explain = explain_prompt("Context bundle here", "Why was this flagged?")
    reconsider = reconsider_prompt("Context bundle here", "Please reconsider the tone call.")

    assert "Preserve intentional prose unless it produces clear reader-facing damage" in explain
    assert "Weigh intentionality, voice logic, and genre payoff" in reconsider


def test_critic_prompt_requires_reader_visible_failures():
    prompt_ctx = build_prompt_context(
        {
            "context_window": ContextWindow(
                target_chunk=_make_chunk("c1", "Wayne said the same old thing again.", 0),
                previous_chunks=[],
                next_chunks=[],
                global_summary="A man fails to be heard by the living.",
            ),
            "genre_intention": GenreIntention(genre="literary_fiction"),
            "document_state": DocumentState(),
        }
    )

    prompt = critic_prompt(prompt_ctx, "cliche_result: {'severity': 0.5}")

    assert "PROSE-CRAFT" in prompt and "NARRATIVE ARCHITECTURE" in prompt
    assert "You are not a proofreader" in prompt
    assert "Distinguish between stylistic intent and actual degradation" in prompt


def test_quick_coach_prompt_is_schema_aligned_and_concrete():
    prompt = quick_coach_prompt(
        "Target section context here.",
        "Help me tighten this transition.",
        current_revision_text="Current revision text goes here.",
    )

    assert "headline: 3-8 words naming the main fix or opportunity." in prompt
    assert "bullets: 1-3 grounded observations; each should explain why it matters for reader effect." in prompt
    assert "try_next: exactly one bounded action the writer can do now (single sentence)." in prompt
    assert "Avoid generic advice like \"improve pacing\"" in prompt
    assert "User focus (optional):\nHelp me tighten this transition." in prompt
    assert "Current revision text goes here." in prompt
    assert "STOP CONDITION" not in prompt


def test_quick_coach_context_includes_latest_critic_panel():
    target = _make_chunk("c2", "Target chunk text.", 1)
    prev = _make_chunk("c1", "Previous context.", 0)
    nxt = _make_chunk("c3", "Next context.", 2)
    bundle = ContextBundle(
        target_chunk=target,
        context_window=ContextWindow(
            target_chunk=target,
            previous_chunks=[prev],
            next_chunks=[nxt],
            global_summary="Summary",
        ),
        document_state=DocumentState(),
        critic_result=CriticResult(
            verdict="weak",
            critique="The scene stalls before the turn.",
            failure_points=["Momentum drops in the second paragraph."],
        ),
    )

    out = slim_narrative_text_from_bundle(bundle)
    assert "LATEST CRITIC PANEL (TARGET CHUNK)" in out
    assert "Verdict: weak" in out
    assert "The scene stalls before the turn." in out
    assert "- Momentum drops in the second paragraph." in out