"""Tests for judgment layer."""

from __future__ import annotations

import pytest
from narrative_dag.nodes.judgment import editor_judge, elasticity_evaluator, report_collector, build_chunk_judgment_entry
from narrative_dag.schemas import EditorJudgment, ElasticityResult


def test_editor_judge():
    state = {"critic_result": None, "defense_result": None, "drift_result": None}
    state["critic_result"] = type("R", (), {"verdict": "borderline", "failure_points": []})()
    state["defense_result"] = type("R", (), {"salvageability": "high"})()
    out = editor_judge(state)
    assert out["editor_judgment"].decision in ("keep", "cut", "rewrite")


def test_elasticity_evaluator():
    state = {"editor_judgment": EditorJudgment(decision="keep", is_drift=False), "drift_result": None}
    out = elasticity_evaluator(state)
    assert "elasticity_result" in out


def test_report_collector():
    state = {"run_id": "run-1", "chunk_judgments": []}
    e = build_chunk_judgment_entry("c1", 0, EditorJudgment(decision="keep"), ElasticityResult())
    state["chunk_judgments"] = [e]
    out = report_collector(state)
    assert out["editorial_report"].run_id == "run-1"
    assert len(out["editorial_report"].chunk_judgments) == 1
