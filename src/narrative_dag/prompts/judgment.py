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


def editor_judgment_prompt(ctx: PromptContext, detector_snapshot: str, critic: str, defense: str) -> str:
    return (
        stage_role_block(
            "the final editorial judge weighing the critic's critique against the advocate's defense",
            [
                "Your job is to render a final, actionable verdict (keep, cut, or rewrite) based on the text and the arguments presented.",
                "Synthesize your thoughts naturally in your reasoning. Do not force artificial categories.",
                "Focus on what the author actually needs to do. If the text works, say so. If it needs a rewrite, be specific about why.",
                "Weigh the defense's argument about the author's underlying intent, but do not ignore genuine execution failures identified by the critic.",
                "SEVERITY SCALE: 0 = No issues, 1 = Minor polish/typos, 2 = Moderate prose/pacing issues, 3 = Significant structural weakness, 4 = Failing its purpose, 5 = Fundamentally broken.",
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
        + "\n\n"
        + format_prompt_context(ctx)
        + "\n\n"
        + stop_condition_judge_block()
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
