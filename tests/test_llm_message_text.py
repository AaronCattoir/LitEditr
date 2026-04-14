"""Regression tests for provider-agnostic assistant text extraction (Gemini 3 blocks, OpenAI, unknown shapes)."""

from __future__ import annotations

from typing import Any

import pytest

from narrative_dag.llm import extract_text_from_ai_message, _normalize_message_content_for_display


class _FakeMessage:
    def __init__(self, content: Any) -> None:
        self.content = content


def test_gemini_style_list_block_with_signature_returns_text_only() -> None:
    huge_sig = "X" * 50_000
    raw = [
        {
            "type": "text",
            "text": "Hello from Gemini.",
            "extras": {"signature": huge_sig},
        }
    ]
    msg = _FakeMessage(raw)
    out = extract_text_from_ai_message(msg)
    assert out == "Hello from Gemini."
    assert "signature" not in out
    assert huge_sig not in out


def test_openai_plain_string_unchanged() -> None:
    msg = _FakeMessage("Plain assistant reply.")
    assert extract_text_from_ai_message(msg) == "Plain assistant reply."


def test_mixed_list_text_and_metadata_only_blocks() -> None:
    raw = [
        {"type": "text", "text": "A"},
        {"type": "thinking", "text": "should be skipped"},
        {"type": "text", "text": "B"},
    ]
    assert extract_text_from_ai_message(_FakeMessage(raw)) == "AB"


def test_unknown_dict_without_text_fails_safe_no_repr_dump() -> None:
    raw = {"unexpected": {"nested": "data"}, "extras": {"signature": "Z" * 10_000}}
    out = extract_text_from_ai_message(_FakeMessage(raw))
    assert out == ""
    assert "signature" not in out
    assert "unexpected" not in out


def test_nested_parts_list() -> None:
    raw = {"parts": [{"type": "text", "text": "Part one"}, {"type": "text", "text": "Part two"}]}
    assert extract_text_from_ai_message(_FakeMessage(raw)) == "Part onePart two"


def test_max_chars_cap() -> None:
    long_text = "a" * 100
    msg = _FakeMessage(long_text)
    assert len(extract_text_from_ai_message(msg, max_chars=20)) == 20


def test_normalize_unknown_atom_returns_empty() -> None:
    class Opaque:
        def __str__(self) -> str:
            return "SHOULD_NOT_APPEAR" * 1000

    assert _normalize_message_content_for_display(Opaque(), _max_chars=100) == ""
