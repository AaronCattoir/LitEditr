"""Judgment prompts."""

from __future__ import annotations

from narrative_dag.prompt_context import format_prompt_context
from narrative_dag.prompts.editorial_policy import editorial_policy_block, stage_role_block
from narrative_dag.schemas import PromptContext


def editor_judgment_prompt(ctx: PromptContext, detector_snapshot: str, critic: str, defense: str) -> str:
    return (
        stage_role_block(
            "the final editorial judge — honest, not diplomatic",
            [
                "Return an advisory keep/cut/rewrite judgment",
                "Evaluate PROSE-CRAFT and NARRATIVE ARCHITECTURE independently in your reasoning",
                "A scene can have clean prose but weak architecture (stalled pacing, undersold turns, "
                "inert exposition) — this still warrants REWRITE",
                "A scene can have rough prose but strong architecture — minor prose fixes warrant REWRITE "
                "at low severity, but acknowledge the structural strength",
                "Do not default to KEEP because the defense makes a reasonable argument — "
                "weigh what the scene actually achieves against what it could achieve",
                "Use the full severity range: 0 = no issues, 1 = minor polish, 2 = meaningful weakness "
                "in one axis, 3 = weakness in both axes or significant structural problem, "
                "4 = scene is failing its purpose, 5 = fundamentally broken",
                "Mechanical-only fixes (typos, punctuation, capitalization) are severity 1; "
                "structural issues start at severity 2",
            ],
        )
        + editorial_policy_block()
        + "\nDetector findings:\n"
        + detector_snapshot
        + "\n\nCritic:\n"
        + critic
        + "\n\nDefense:\n"
        + defense
        + "\n\n"
        + format_prompt_context(ctx)
    )


def elasticity_prompt(ctx: PromptContext, judgment: str, drift: str) -> str:
    return (
        stage_role_block(
            "an elasticity evaluator deciding whether deviation should be preserved",
            [
                "Treat first-person filtering, genre convention, and deliberate taste as possible reasons to preserve deviation",
                "Only override drift when the deviation creates meaningful payoff or stronger voice",
                "If the deviation merely coasts without adding pressure or payoff, do not preserve it — "
                "inertia is not intention",
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
