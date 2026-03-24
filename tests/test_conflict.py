"""Tests for conflict layer: critic and defense."""

from __future__ import annotations

import pytest
from narrative_dag.nodes.conflict import critic_agent, defense_agent
from narrative_dag.schemas import CriticResult, ClicheResult


def test_critic_agent():
    state = {"drift_result": None, "cliche_result": ClicheResult(cliche_flags=["at the end of the day"], severity=0.5), "vagueness_result": None}
    out = critic_agent(state)
    assert "critic_result" in out
    assert out["critic_result"].verdict in ("fail", "weak", "borderline")


def test_defense_after_critic():
    state = {"drift_result": None, "cliche_result": ClicheResult(severity=0.0), "vagueness_result": None}
    state.update(critic_agent(state))
    out = defense_agent(state)
    assert "defense_result" in out
    assert out["defense_result"].salvageability in ("high", "medium", "low")
