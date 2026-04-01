"""Conflict prompts."""

from __future__ import annotations

from narrative_dag.prompt_context import format_prompt_context
from narrative_dag.prompts.editorial_policy import (
    editorial_policy_block,
    evaluation_gate_block,
    stage_role_block,
    stop_condition_critic_block,
    stop_condition_defense_block,
)
from narrative_dag.schemas import PromptContext


def critic_prompt(ctx: PromptContext, detector_snapshot: str) -> str:
    return (
        stage_role_block(
            "an objective and incisive editorial critic",
            [
                """Structure your critique to identify specific, actionable weaknesses in both PROSE-CRAFT and NARRATIVE ARCHITECTURE.

PROSE-CRAFT:
- Flag dead language, mechanical errors, weak imagery, or rhythm breaks.
- Cite exact phrases and explain why they weaken the sentence.
- Distinguish between stylistic intent and actual degradation (do not overcorrect intentional voice).

NARRATIVE ARCHITECTURE:
- Evaluate pacing, escalation, scene movement, and structural clarity.
- Identify if the scene fails to achieve its intended function (e.g., lacks tension, muddled reveal, static character).

FORCING FUNCTION:
- Write a clear, direct critique paragraph detailing the most significant issues.
- Identify the most damaging flaw in the scene and cite evidence.
- Determine the overall verdict (fail, weak, or borderline).

CONSTRAINTS:
- Be specific and cite text directly.
- Avoid vague platitudes.
- Do not invent flaws if the text is fundamentally working, but do not ignore genuine weaknesses.""",
            ],
        )
        + "\n"
        + evaluation_gate_block()
        + "\n"
        + editorial_policy_block()
        + "\nDetector findings:\n"
        + detector_snapshot
        + "\n\n"
        + format_prompt_context(ctx)
        + "\n\n"
        + stop_condition_critic_block()
    )


def defense_prompt(ctx: PromptContext, detector_snapshot: str, critique: str) -> str:
    return (
        stage_role_block(
            "an editorial advocate who argues for the text's underlying intent against the critic",
            [
                """Your purpose is to find the merit in the text, push back against the critic's judgments, and advocate for the writer's vision. Act as the text's defense attorney.

DEFENSE STRATEGY:
- Rebuttal: Address the critic's main argument directly. Reject the premise if they are applying the wrong standard (e.g., judging voice-driven prose by strict grammatical elegance), or argue that perceived "flaws" are actually deliberate stylistic choices.
- Merit: Highlight the latent emotional resonance or narrative potential in moments the critic dismissed. Point out what actually works on the page.
- Salvage: If the execution is genuinely flawed, defend the *intent* behind the choice and explain how the underlying instinct could be preserved while fixing the execution.

FORCING FUNCTION:
- Write a structured, constructive defense paragraph.
- Identify specific 'valid points' (moments of actual strength) in the text that support your defense.
- Determine the salvageability of the scene (high, medium, or low).

CONSTRAINTS:
- Do NOT act as a second evaluator or simply agree with the critic.
- You may concede genuine execution errors, but always pivot to defending the underlying intent.
- Be specific and cite text directly."""
            ],
        )
        + "\n"
        + evaluation_gate_block()
        + "\n"
        + editorial_policy_block()
        + "\nDetector findings:\n"
        + detector_snapshot
        + "\n\nCritic output:\n"
        + critique
        + "\n\n"
        + format_prompt_context(ctx)
        + "\n\n"
        + stop_condition_defense_block()
    )
