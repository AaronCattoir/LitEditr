"""Detection prompts."""

from __future__ import annotations

from narrative_dag.prompt_context import format_prompt_context
from narrative_dag.prompts.editorial_policy import editorial_policy_block, stage_role_block
from narrative_dag.schemas import PromptContext


DETECTOR_GUIDANCE = {
    "drift": [
        "Compare the chunk against the declared story point, genre, and recent trajectory",
        "Do not call ordinary first-person subjectivity, repression, or rough idiom drift",
        "Flag drift only when the prose pulls the story into the wrong mode or psychology",
        "drift_type must be exactly one of: tone, syntax, psychological, narrative, or empty string if none applies",
    ],
    "cliche": [
        "Flag dead language, borrowed stock moves, or unearned familiar beats",
        "Do not punish colloquial voice, regional speech, or load-bearing genre texture",
        "Prefer precision over recall; silence is better than false positives",
    ],
    "vagueness": [
        "Focus on reader-facing blur, not purposeful withholding",
        "Allow ambiguity when it creates pressure, mystery, or emotional truth",
    ],
    "emotional_honesty": [
        "Judge whether the text earns its emotional signal on the page",
        "Account for repression, stoicism, denial, and unreliable first-person filtering",
        "Ask whether the emotional beat lands with full force or coasts on implication — "
        "restraint is valid but undercooked is not the same as restrained",
        "Flag scenes where the emotional architecture is present but underdeveloped: "
        "the setup exists but the payoff is soft, or a turn is implied rather than delivered",
    ],
    "redundancy": [
        "Compare against the recent narrative trajectory, not the target chunk alone",
        "Flag only repetition that stalls movement or replays the same idea without gain",
        "Also flag scenes that tread water — where prose moves forward but the story's emotional "
        "or narrative position does not materially advance from where the previous chunk ended",
    ],
    "risk": [
        "Differentiate bold, purposeful risk from failed execution",
        "A risky choice that creates pressure, surprise, or thematic payoff can still be working",
        "Do not default to 'payoff — working' — ask whether the risk fully pays off or merely attempts to",
        "Flag risks that are partially realized: the ambition is visible but the execution "
        "undersells the moment, leaving pressure on the table",
    ],
}


def detector_prompt(
    detector_name: str,
    ctx: PromptContext,
    *,
    paragraph_intent: str = "",
    voice_profile: dict | None = None,
) -> str:
    guidance = DETECTOR_GUIDANCE.get(detector_name, [])
    extra = []
    if paragraph_intent:
        extra.append(f"Paragraph intent: {paragraph_intent}")
    if voice_profile:
        extra.append(f"Current voice profile: {voice_profile}")
    extra_block = ("\n".join(extra) + "\n\n") if extra else ""

    return (
        stage_role_block(
            f"the {detector_name} detector for a narrative editorial pipeline",
            guidance + ["Return only the requested structured output schema."],
        )
        + editorial_policy_block()
        + "\n"
        + extra_block
        + format_prompt_context(ctx)
    )
