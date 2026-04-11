"""Heuristic evidence spans for UI highlights when the LLM omits structured spans."""

from __future__ import annotations

from narrative_dag.schemas import CriticResult, DefenseResult, EditorJudgment, EvidenceSpan


def _normalize_spans_against_chunk(
    spans: list[EvidenceSpan],
    chunk_start: int,
    chunk_end: int,
    chunk_text: str,
) -> list[EvidenceSpan]:
    """Clamp LLM or client spans to the current chunk's document range; drop invalid overlaps."""
    out: list[EvidenceSpan] = []
    seen: set[tuple[int, int]] = set()
    for s in spans:
        try:
            a, b = int(s.start_char), int(s.end_char)
        except (TypeError, ValueError):
            continue
        if b <= a or chunk_end <= chunk_start:
            continue
        lo = max(a, chunk_start)
        hi = min(b, chunk_end)
        if hi <= lo:
            continue
        key = (lo, hi)
        if key in seen:
            continue
        seen.add(key)
        # Always rebuild quote from normalized range so UI stale checks
        # compare against ground-truth text, even when LLM spans were clamped.
        local_lo = lo - chunk_start
        local_hi = hi - chunk_start
        quote = chunk_text[local_lo:local_hi]
        if len(quote) > 4000:
            quote = quote[:4000]
        label = (s.label or "evidence").strip()[:200] or "evidence"
        out.append(EvidenceSpan(start_char=lo, end_char=hi, quote=quote, label=label))
    out.sort(key=lambda x: (x.start_char, x.end_char))
    return out


def _phrase_candidates(phrases: list[str]) -> list[str]:
    """Expand long phrases into shorter search needles (sentence-ish + sliding prefix)."""
    seen: set[str] = set()
    out: list[str] = []
    for raw in phrases:
        q = (raw or "").strip()
        if len(q) < 3:
            continue
        for part in q.replace("?", ".").split("."):
            p = part.strip()
            if len(p) >= 12 and p not in seen:
                seen.add(p)
                out.append(p)
        if q not in seen:
            seen.add(q)
            out.append(q)
        for n in (80, 50, 30):
            if len(q) > n:
                frag = q[:n].strip()
                if len(frag) >= 12 and frag not in seen:
                    seen.add(frag)
                    out.append(frag)
    return out


def _infer_spans(chunk_text: str, base_offset: int, phrases: list[str]) -> list[EvidenceSpan]:
    spans: list[EvidenceSpan] = []
    if not chunk_text:
        return spans
    tl = chunk_text.lower()
    seen: set[tuple[int, int]] = set()
    for q in _phrase_candidates(phrases):
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
    base, text = _chunk_text_and_base(state)
    chunk_end = base + len(text)
    if result.evidence_spans:
        norm = _normalize_spans_against_chunk(list(result.evidence_spans), base, chunk_end, text)
        return result.model_copy(update={"evidence_spans": norm})
    phrases = list(result.failure_points) + ([result.critique[:120]] if result.critique else [])
    spans = _infer_spans(text, base, phrases)
    if not spans:
        if text:
            # Last-resort marker so UI still has an inline anchor for flagged chunks.
            end = min(len(text), 220)
            return result.model_copy(
                update={
                    "evidence_spans": [
                        EvidenceSpan(
                            start_char=base,
                            end_char=base + end,
                            quote=text[:end],
                            label="fallback",
                        )
                    ]
                }
            )
        return result
    return result.model_copy(update={"evidence_spans": spans})


def fill_defense_spans(state: dict, result: DefenseResult) -> DefenseResult:
    base, text = _chunk_text_and_base(state)
    chunk_end = base + len(text)
    if result.evidence_spans:
        norm = _normalize_spans_against_chunk(list(result.evidence_spans), base, chunk_end, text)
        return result.model_copy(update={"evidence_spans": norm})
    phrases = list(result.valid_points) + ([result.defense[:120]] if result.defense else [])
    spans = _infer_spans(text, base, phrases)
    if not spans:
        return result
    return result.model_copy(update={"evidence_spans": spans})


def fill_judgment_spans(state: dict, result: EditorJudgment) -> EditorJudgment:
    base, text = _chunk_text_and_base(state)
    chunk_end = base + len(text)
    if result.evidence_spans:
        norm = _normalize_spans_against_chunk(list(result.evidence_spans), base, chunk_end, text)
        return result.model_copy(update={"evidence_spans": norm})
    phrases = []
    if result.core_issue:
        phrases.append(result.core_issue)
    if result.guidance:
        phrases.append(result.guidance[:160])
    spans = _infer_spans(text, base, phrases)
    if not spans:
        if text and (result.core_issue or result.guidance):
            end = min(len(text), 220)
            return result.model_copy(
                update={
                    "evidence_spans": [
                        EvidenceSpan(
                            start_char=base,
                            end_char=base + end,
                            quote=text[:end],
                            label="fallback",
                        )
                    ]
                }
            )
        return result
    return result.model_copy(update={"evidence_spans": spans})
