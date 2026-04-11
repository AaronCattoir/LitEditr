"""Format quick-coach structured advice as plain text for story-chat turns."""

from __future__ import annotations

from narrative_dag.schemas import QuickCoachAdvice

QUICK_COACH_STORY_CHAT_USER_MESSAGE = "Quick coach for this section."


def format_quick_coach_advice_for_chat(advice: QuickCoachAdvice) -> str:
    """Plain-text lines for chat bubbles (no markdown)."""
    parts: list[str] = []
    h = (advice.headline or "").strip()
    if h:
        parts.append(h)
    for b in advice.bullets or []:
        t = (b or "").strip()
        if t:
            parts.append(f"• {t}")
    tn = (advice.try_next or "").strip()
    if tn:
        parts.append(f"Try next: {tn}")
    return "\n".join(parts) if parts else "(No quick coach output.)"
