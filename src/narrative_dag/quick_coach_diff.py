"""Thresholds for quick coach: current revision text vs last analyzed chunk."""

from __future__ import annotations

import narrative_dag.config as config_module


def quick_coach_oob_threshold(analyzed_len: int) -> int:
    """Max allowed absolute character delta before quick coach refuses (inclusive)."""
    raw = int(analyzed_len * config_module.QUICK_COACH_OOB_RATIO)
    return max(
        config_module.QUICK_COACH_OOB_MIN_CHARS,
        min(config_module.QUICK_COACH_OOB_MAX_CHARS, raw),
    )


def quick_coach_char_delta(analyzed: str, current: str) -> int:
    return abs(len(analyzed) - len(current))


def is_quick_coach_oob(analyzed: str, current: str) -> tuple[bool, int, int]:
    """Return (is_oob, delta_chars, threshold_chars)."""
    alen = len(analyzed)
    thr = quick_coach_oob_threshold(alen)
    delta = quick_coach_char_delta(analyzed, current)
    return (delta > thr, delta, thr)
