"""Prompt for sparkle quick-coach: concise, concrete revision guidance."""


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

Compare baseline vs current. Focus on the delta: what improved, what weakened, and the single most useful next move.
"""
    return f"""You are a concise fiction coach. Give exactly ONE concrete revision handle for the target section.

Write guidance that is immediately usable:
- Be specific about the moment to revise (sentence, paragraph, transition, or beat).
- Avoid generic advice like "improve pacing" unless tied to a concrete place in the text.
- Preserve working prose; do not suggest cosmetic line edits when the scene already lands.
- Prioritize scene purpose, pressure/stakes, clarity, and character consistency with the global map.

Output shape requirements:
- headline: 3-8 words naming the main fix or opportunity.
- bullets: 1-3 grounded observations; each should explain why it matters for reader effect.
- try_next: exactly one bounded action the writer can do now (single sentence).

Use short quoted snippets only when helpful for precision. Keep the full response concise.

{narrative_context_text}
{diff_block}
{focus_block}

Respond using the required structured format only."""

