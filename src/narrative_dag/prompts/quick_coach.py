"""Prompt for sparkle quick-coach: brief advice only, no full editorial pipeline."""

from narrative_dag.prompts.editorial_policy import evaluation_gate_block, stop_condition_critic_block


def quick_coach_prompt(
    narrative_context_text: str,
    focus: str,
    *,
    current_revision_text: str | None = None,
) -> str:
    """Single-turn coach note given formatted narrative + section context."""
    focus_block = f"\n\nUser focus (optional):\n{focus.strip()}\n" if (focus or "").strip() else ""
    diff_block = ""
    if current_revision_text is not None:
        diff_block = f"""

--- Last analyzed version of this section (baseline) ---
The narrative context above reflects this baseline unless noted.

--- Current saved revision of this section (what the author sees now) ---
{current_revision_text}

Compare baseline vs current. Comment on what changed and whether the edit improves clarity, voice, or stakes. One concrete next step.
"""
    return f"""You are a concise fiction coach. Give ONE short piece of actionable advice for the target section below.
Do not run a full critique pipeline. No detectors, no critic/defense framing. Stay under ~200 words of reasoning in the structured fields.
Prioritize: clarity, scene purpose, character consistency with the global map, and one concrete revision suggestion.
Preserve working prose: do not suggest rewrites for marginal polish.

{evaluation_gate_block()}

{narrative_context_text}
{diff_block}
{focus_block}

{stop_condition_critic_block()}

Respond using the required structured format only."""

