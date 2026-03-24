"""Heuristic evidence spans for UI highlights when the LLM omits structured spans."""

from __future__ import annotations

from narrative_dag.schemas import CriticResult, DefenseResult, EditorJudgment, EvidenceSpan


def _infer_spans(chunk_text: str, base_offset: int, phrases: list[str]) -> list[EvidenceSpan]:
    spans: list[EvidenceSpan] = []
    if not chunk_text:
        return spans
    tl = chunk_text.lower()
    seen: set[tuple[int, int]] = set()
    for p in phrases:
        q = (p or "").strip()
        if len(q) < 3:
            continue
        needle = q[:80].lower()
        i = tl.find(needle)
        if i < 0 and len(needle) > 20:
            i = tl.find(needle[:20])
        if i < 0:
            continue
        end_local = min(len(chunk_text), i + len(q))
        key = (i, end_local)
        if key in seen:
            continue
        seen.add(key)
        spans.append(
            EvidenceSpan(
                start_char=base_offset + i,
                end_char=base_offset + end_local,
                quote=chunk_text[i:end_local],
                label="evidence",
            )
        )
        if len(spans) >= 8:
            break
    return spans


def _chunk_text_and_base(state: dict) -> tuple[int, str]:
    ctx = state.get("context_window")
    if ctx is None:
        return 0, ""
    if isinstance(ctx, dict):
        tc = ctx.get("target_chunk") or {}
        return int(tc.get("start_char", 0)), str(tc.get("text", ""))
    tc = ctx.target_chunk
    return int(tc.start_char), str(tc.text)


def fill_critic_spans(state: dict, result: CriticResult) -> CriticResult:
    if result.evidence_spans:
        return result
    base, text = _chunk_text_and_base(state)
    phrases = list(result.failure_points) + ([result.critique[:120]] if result.critique else [])
    spans = _infer_spans(text, base, phrases)
    if not spans:
        return result
    return result.model_copy(update={"evidence_spans": spans})


def fill_defense_spans(state: dict, result: DefenseResult) -> DefenseResult:
    if result.evidence_spans:
        return result
    base, text = _chunk_text_and_base(state)
    phrases = list(result.valid_points) + ([result.defense[:120]] if result.defense else [])
    spans = _infer_spans(text, base, phrases)
    if not spans:
        return result
    return result.model_copy(update={"evidence_spans": spans})


def fill_judgment_spans(state: dict, result: EditorJudgment) -> EditorJudgment:
    if result.evidence_spans:
        return result
    base, text = _chunk_text_and_base(state)
    phrases = []
    if result.core_issue:
        phrases.append(result.core_issue)
    if result.guidance:
        phrases.append(result.guidance[:160])
    spans = _infer_spans(text, base, phrases)
    if not spans:
        return result
    return result.model_copy(update={"evidence_spans": spans})
