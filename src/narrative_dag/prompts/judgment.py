"""Judgment prompts."""

from __future__ import annotations

from narrative_dag.prompt_context import format_prompt_context
from narrative_dag.prompts.editorial_policy import (
    editorial_policy_block,
    evaluation_gate_block,
    stage_role_block,
    stop_condition_judge_block,
)
from narrative_dag.schemas import PromptContext


def editor_judgment_prompt(
    ctx: PromptContext,
    detector_snapshot: str,
    critic: str,
    defense: str,
    *,
    dialectic_mediation: str | None = None,
    dialectic_synthesis: str | None = None,
) -> str:
    mediation_block = (
        "\n\nDialectic mediation (prior structured analysis — use as insight; do not merely repeat):\n" + dialectic_mediation + "\n"
        if dialectic_mediation
        else ""
    )
    synthesis_block = (
        "\n\nDialectic synthesis (prior higher-level framing — use as insight; do not merely repeat):\n"
        + dialectic_synthesis
        + "\n"
        if dialectic_synthesis
        else ""
    )
    return (
        stage_role_block(
            "the final editorial judge weighing the critic's critique against the advocate's defense",
            [
                "Your job is to render a final, actionable verdict (keep, cut, or rewrite) based on the text and the arguments presented.",
                "When dialectic mediation or synthesis is provided, treat it as supporting analysis of the debate — integrate it into your reasoning without copying it verbatim.",
                "Synthesize your thoughts naturally in your reasoning. Do not force artificial categories.",
                "Focus on what the author actually needs to do. If the text works, say so. If it needs a rewrite, be specific about why.",
                "Weigh the defense's argument about the author's underlying intent, but do not ignore genuine execution failures identified by the critic.",
                "SCOPE: Your verdict, core issue, and guidance must be confined to the TARGET CHUNK only. Previous and next context inform your understanding of narrative position; they are not targets for critique. Do not recommend cuts or rewrites to chunks outside the target.",
                "SEVERITY SCALE: 0 = No issues. 1 = Minor mechanical errors (typos, punctuation). 2 = Prose-level weakness: dead language, rhythm failures, weak imagery — voice intact but underperforming. 3 = Structural deficit: scene moves but undersells its beat, tension described not constructed, emotional position unchanged by scene end. 4 = Scene failing its purpose: stakes absent, dread stated not built, character static, no narrative movement. 5 = Fundamentally broken: incoherent, contradicts story logic, or actively damages reader engagement. NOTE: 'readable and tonally consistent' maps to severity 1–2 at most, never 0, unless the scene also moves and lands.",
            ],
        )
        + "\n"
        + evaluation_gate_block()
        + "\n"
        + editorial_policy_block()
        + "\nDetector findings:\n"
        + detector_snapshot
        + "\n\nCritic:\n"
        + critic
        + "\n\nDefense:\n"
        + defense
        + mediation_block
        + synthesis_block
        + "\n"
        + format_prompt_context(ctx)
        + "\n\n"
        + stop_condition_judge_block()
    )


def evidence_synthesis_prompt(ctx: PromptContext, critic: str, defense: str) -> str:
    return (
        stage_role_block(
            "a synthesis agent mapping the editorial debate directly to the text",
            [
                "Your job is to identify the exact verbatim spans in the TARGET CHUNK that the critic and advocate are debating.",
                "For each span, provide a short, plain language synthesis (one sentence) of the critic's point and the advocate's point.",
                "Return only high-signal spans: each quote should be contiguous text from the TARGET CHUNK, usually 6-24 words, and not a whole paragraph.",
                "Also return start_char and end_char as 0-based character offsets INSIDE the TARGET CHUNK text (end exclusive).",
                "Offsets and quote must agree exactly. If uncertain, skip that span rather than guessing.",
                "If the debate is broad, choose 1-3 representative spans rather than many weak spans.",
            ],
        )
        + "\n\nCritic:\n"
        + critic
        + "\n\nAdvocate/Defense:\n"
        + defense
        + "\n\n"
        + format_prompt_context(ctx)
    )


def elasticity_prompt(ctx: PromptContext, judgment: str, drift: str) -> str:
    return (
        stage_role_block(
            "an elasticity evaluator deciding whether a stylistic deviation should be preserved",
            [
                "Evaluate if the detected drift is a deliberate, effective choice (e.g., character voice, genre convention, psychological filtering) rather than a mistake.",
                "Only override the drift warning if the deviation creates a meaningful payoff or stronger voice.",
                "If the deviation is just sloppy or coasts without adding narrative pressure, it should not be preserved.",
            ],
        )
        + editorial_policy_block()
        + "\nJudgment:\n"
        + judgment
        + "\n\nDrift signal:\n"
        + drift
        + "\n\n"
        + format_prompt_context(ctx)
    )
