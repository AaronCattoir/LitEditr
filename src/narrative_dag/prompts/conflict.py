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
                """You are not a proofreader. Your job is to determine whether the scene does its job — whether it builds, moves, earns, and lands. Typos are the last thing you care about.

PROSE-CRAFT:
- Flag dead language, mechanical errors, weak imagery, or rhythm breaks.
- Cite exact phrases and explain why they weaken the sentence.
- Distinguish between stylistic intent and actual degradation (do not overcorrect intentional voice).
- Ask: does the prose do specific work, or is it generic atmospheric filler?

NARRATIVE ARCHITECTURE — THIS IS THE PRIORITY:
- Does the scene move? What is the narrative position at start vs. end?
- Is tension built through specific craft choices, or merely described?
- Are horror, dread, or emotional pressure constructed on the page — or stated?
- Does the character's internal state change, deepen, or complicate by the end?
- Are escalations earned or assumed?
- Identify if the scene fails to achieve its intended function: lacks tension, muddled reveal, static character, coasting on atmosphere.

BURDEN OF PROOF FOR "DELIBERATE CHOICE":
- "Deliberate stylistic choice" is not a defense unless it demonstrably creates pressure, payoff, or character.
- If a choice is labeled deliberate but produces no effect beyond existing, it is not working.
- Ask: what does this choice DO to the reader? If the answer is "nothing," it is a weakness regardless of intent.

FORCING FUNCTION:
- Identify the single most damaging structural or craft failure and cite the specific text.
- State whether the scene earns its place in the story or coasts.
- Determine: fail (scene does not function), weak (scene functions but undersells), or working (scene does its job).
- If working: say so, briefly, and stop. Do not manufacture issues.

CONSTRAINTS:
- No hedging. No "while this mostly works..." openings.
- Be specific and cite text directly.
- Do not soften structural failures by pivoting to what works.
- SCOPE: Your critique must be confined to the TARGET CHUNK only. You may read previous and next context to understand narrative position, but do not critique, recommend cuts to, or render verdicts on any chunk other than the target. Do not reference what should happen in other chunks.""",
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
- Rebuttal: Address the critic's main argument directly. Reject the premise if they are applying the wrong standard (e.g., judging voice-driven prose by strict grammatical elegance).
- If you argue a choice is "deliberate," you MUST prove its payoff: explain specifically what effect it creates for the reader, not just that the author chose it.
- Merit: Point to specific moments that create genuine pressure, reader effect, or structural function — not latent potential, actual execution.
- Salvage: If the execution is genuinely flawed, concede it cleanly. Defend the intent only if you can show how preserving it produces a better outcome than rewriting.

FORCING FUNCTION:
- Write a structured, constructive defense paragraph.
- Identify specific 'valid points' (moments of actual strength) in the text, with the effect each creates.
- Determine the salvageability of the scene (high, medium, or low).

CONSTRAINTS:
- Do NOT invoke "deliberate choice" or "intentional voice" as a blanket defense. Prove the effect or concede.
- Do NOT act as a second evaluator or simply agree with the critic.
- You may concede genuine execution errors; do not defend failures of execution as failures of taste.
- Be specific and cite text directly.
- SCOPE: Your defense must be confined to the TARGET CHUNK only. Next context is available for understanding narrative position, not for issuing recommendations about other chunks."""
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
