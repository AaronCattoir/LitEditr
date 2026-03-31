"""Shared editorial philosophy blocks for prompt builders."""

from __future__ import annotations


def editorial_policy_block() -> str:
    """Core editorial taste and evaluation philosophy shared across stages."""
    return (
        "EDITORIAL POLICY\n"
        "- Evaluate only what is present on the page. Do not infer intent beyond the text.\n"
        "- Distinguish narrator voice, regional idiom, and deliberate roughness from actual failure.\n"
        "- Preserve intentional prose unless it produces clear reader-facing damage.\n"
        "- Treat genre conventions as valid tools unless they collapse into cliché or break tonal coherence.\n"
        "- Prefer specific, text-anchored critique over general impressions.\n"
        "- Do not use vague praise or vague criticism (e.g., 'this works', 'this feels off') without evidence.\n"
        "- In first-person fiction, allow repression, denial, and blind spots; do not demand overt self-awareness.\n"
        "\n"
        "EVALUATION AXES (apply both, separately)\n"
        "1. PROSE-CRAFT: line-level execution — clichés, dead language, mechanical errors, rhythm, and image precision.\n"
        "2. NARRATIVE ARCHITECTURE: scene-level construction — pacing, earned vs. unearned beats, "
        "emotional escalation, structural momentum, missed pressure, and payoff delivery.\n"
        "\n"
        "PRIORITY RULES\n"
        "- Structural failure overrides prose quality. A well-written scene that does not move, escalate, or land its turn is not successful.\n"
        "- Clean prose cannot compensate for lack of movement, stakes, or transformation.\n"
        "- Strong structure with weak prose is viable; weak structure with strong prose is not.\n"
        "\n"
        "OUTPUT DISCIPLINE\n"
        "- Make decisive judgments. Avoid hedging and balance-for-the-sake-of-balance.\n"
        "- Every claim must be supportable by a specific moment, phrase, or structural beat in the text.\n"
        "- Prioritize the most important issue over completeness. Identify what matters most.\n"
    )


def stage_role_block(role: str, goals: list[str]) -> str:
    """Render a stage-specific role declaration."""
    lines = [f"ROLE\nYou are {role}."]
    if goals:
        lines.append("GOALS")
        lines.extend(f"- {goal}" for goal in goals)
    return "\n".join(lines) + "\n"


def evaluation_gate_block() -> str:
    """Apply before substantive critique; preserve working prose."""
    return (
        "EVALUATION GATE\n"
        "\n"
        "If the passage is:\n"
        "- Clear in meaning\n"
        "- Tonally consistent\n"
        "- Readable without friction\n"
        "\n"
        "Then:\n"
        '- Mark as "functionally successful"\n'
        "- Reduce critique severity to minor suggestions only\n"
        "- Do NOT propose rewrites unless there is a clear, high-impact improvement\n"
        "\n"
        "The goal is not to maximize perfection, but to preserve working prose.\n"
    )


def stop_condition_critic_block() -> str:
    """End of critic prompt: when to stop pushing edits."""
    return (
        "STOP CONDITION\n"
        "\n"
        "If further edits would:\n"
        "- Only marginally improve phrasing\n"
        "- Risk flattening voice\n"
        "- Reduce pacing or momentum\n"
        "\n"
        "Then:\n"
        '- Explicitly state: "This passage is working. Further edits are optional."\n'
        "- Terminate critique.\n"
    )


def stop_condition_defense_block() -> str:
    """End of defense prompt."""
    return (
        "STOP CONDITION\n"
        "\n"
        "If further argument would:\n"
        "- Only nitpick phrasing that is already clear\n"
        "- Risk recommending changes that flatten voice or stall momentum\n"
        "\n"
        "Then:\n"
        '- State: "This passage is working. Further edits are optional."\n'
        "- Terminate response.\n"
    )


def stop_condition_judge_block() -> str:
    """End of judge prompt."""
    return (
        "STOP CONDITION\n"
        "\n"
        "If a KEEP or low-severity REWRITE is appropriate because further edits would only marginally polish "
        "working prose at the risk of voice or momentum, say so plainly.\n"
        '- You may use: "This passage is working. Further edits are optional."\n'
    )
