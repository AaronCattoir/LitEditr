"""Dialectic mediator and synthesis prompts (internal; before editor judgment)."""

from __future__ import annotations

from narrative_dag.prompt_context import format_prompt_context
from narrative_dag.prompts.editorial_policy import editorial_policy_block, stage_role_block
from narrative_dag.schemas import PromptContext


def dialectic_mediation_prompt(ctx: PromptContext, critic: str, defense: str) -> str:
    return (
        stage_role_block(
            "the impartial chair of a panel mediating between an editorial critic and an advocate",
            [
                "Analyze the arguments presented for both the critic's position and the advocate's position.",
                "Identify the strongest points of each argument.",
                "Where do they directly contradict each other?",
                "What are the underlying assumptions and values that drive each position?",
                "What are the limitations of both perspectives?",
                "Provide a clear and structured summary of the core tension between the two views.",
                "Do NOT produce a final editorial verdict (keep/cut/rewrite) and do NOT prescribe rewrites to the prose.",
                "Do NOT yet create a concluding dialectical synthesis that resolves the debate — that is a separate step when enabled.",
                "SCOPE: Confine analysis to the TARGET CHUNK; surrounding context informs position only.",
            ],
        )
        + "\n"
        + editorial_policy_block()
        + "\n\nCritic (structured output):\n"
        + critic
        + "\n\nAdvocate / defense (structured output):\n"
        + defense
        + "\n\n"
        + format_prompt_context(ctx)
    )


def dialectic_synthesis_prep_prompt(
    ctx: PromptContext,
    critic: str,
    defense: str,
    mediation_json: str,
) -> str:
    return (
        stage_role_block(
            "an editorial dialectician producing a higher-level synthesis after mediation",
            [
                "You have already summarized the tension between critic and advocate (mediation).",
                "Your task is to create a dialectical synthesis: NOT a simple middle-ground or bland summary.",
                "Produce a new perspective that incorporates valid insights from both arguments.",
                "Address how the core contradictions between them might be resolved at the level of craft and intent.",
                "Transcend the original terms of the debate where appropriate to give a more comprehensive understanding.",
                "Do NOT output a final editorial verdict (keep/cut/rewrite) for the manuscript — the judge will do that next.",
                "SCOPE: Confine to the TARGET CHUNK as the locus of debate; context informs only.",
            ],
        )
        + "\n"
        + editorial_policy_block()
        + "\n\nCritic:\n"
        + critic
        + "\n\nAdvocate / defense:\n"
        + defense
        + "\n\nPrior mediation (structured):\n"
        + mediation_json
        + "\n\n"
        + format_prompt_context(ctx)
    )
