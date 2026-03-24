"""Shared editorial philosophy blocks for prompt builders."""

from __future__ import annotations


def editorial_policy_block() -> str:
    """Core editorial taste and evaluation philosophy shared across stages."""
    return (
        "EDITORIAL POLICY\n"
        "- Evaluate what is on the page, not what a generic workshop might prefer.\n"
        "- Distinguish narrator voice, regional idiom, and deliberate roughness from authorial weakness.\n"
        "- Preserve intentional prose unless it causes reader-facing damage.\n"
        "- Treat genre conventions as valid tools unless they read as dead language or break the story's mode.\n"
        "- Prefer evidence-backed critique over surface heuristics.\n"
        "- Reward specificity, pressure, atmosphere, emotional honesty, and thematic payoff.\n"
        "- In first-person fiction, allow repression, denial, and blind spots; do not demand overt self-awareness.\n"
        "\n"
        "EVALUATION AXES (apply both, separately)\n"
        "1. PROSE-CRAFT: line-level execution — clichés, dead language, mechanical errors, rhythm, image precision.\n"
        "2. NARRATIVE ARCHITECTURE: scene-level construction — pacing, earned vs. unearned beats, "
        "emotional escalation, structural momentum, missed opportunities for pressure or payoff, "
        "whether exposition pulls its weight, whether the scene's turn lands with full force.\n"
        "Do not let clean prose mask structural weakness or pacing drift. "
        "A well-written scene that stalls, repeats, or undersells its own stakes still needs work.\n"
    )


def stage_role_block(role: str, goals: list[str]) -> str:
    """Render a stage-specific role declaration."""
    lines = [f"ROLE\nYou are {role}."]
    if goals:
        lines.append("GOALS")
        lines.extend(f"- {goal}" for goal in goals)
    return "\n".join(lines) + "\n"
