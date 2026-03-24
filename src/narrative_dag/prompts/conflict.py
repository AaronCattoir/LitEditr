"""Conflict prompts."""

from __future__ import annotations

from narrative_dag.prompt_context import format_prompt_context
from narrative_dag.prompts.editorial_policy import editorial_policy_block, stage_role_block
from narrative_dag.schemas import PromptContext


def critic_prompt(ctx: PromptContext, detector_snapshot: str) -> str:
    return (
        stage_role_block(
            "a rigorous editorial critic who refuses to flatter",
            [
                "Structure your critique in two sections: PROSE-CRAFT and NARRATIVE ARCHITECTURE",
                "PROSE-CRAFT: flag dead language, mechanical errors, image failures, rhythm breaks — cite the exact words",
                "NARRATIVE ARCHITECTURE: evaluate pacing, emotional escalation, scene construction, "
                "whether exposition earns its place, whether the scene's turn lands with full force, "
                "and whether beats are underdeveloped or undersold",
                "Do not confuse intentional voice or genre texture with damage",
                "Do not let strong prose excuse structural weakness — a well-written scene can still stall or undersell its stakes",
                "Ask: what is this scene trying to do, and does it fully achieve it? If not, name the gap",
            ],
        )
        + editorial_policy_block()
        + "\nDetector findings:\n"
        + detector_snapshot
        + "\n\n"
        + format_prompt_context(ctx)
    )


def defense_prompt(ctx: PromptContext, detector_snapshot: str, critique: str) -> str:
    return (
        stage_role_block(
            "an editorial defense agent",
            [
                "Respond to both PROSE-CRAFT and NARRATIVE ARCHITECTURE sections of the critique",
                "Steelman choices that may be intentional and worth preserving — argue from voice logic, "
                "genre logic, emotional truth, and thematic payoff",
                "Concede prose-craft issues when the critic cites specific dead language or mechanical errors",
                "Concede architectural issues when the critic identifies stalled momentum, "
                "underdeveloped turns, or exposition that does not earn its page-time",
                "Intentionality alone does not equal quality — a deliberate choice can still underperform",
                "Do not defend a scene by re-describing what it does; explain why what it does works better "
                "than what the critic proposes",
            ],
        )
        + editorial_policy_block()
        + "\nDetector findings:\n"
        + detector_snapshot
        + "\n\nCritic output:\n"
        + critique
        + "\n\n"
        + format_prompt_context(ctx)
    )
