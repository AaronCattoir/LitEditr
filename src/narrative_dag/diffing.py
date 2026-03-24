"""Text diff helpers for invalidating chunk spans after edits."""

from __future__ import annotations

import hashlib
from difflib import SequenceMatcher


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def affected_char_ranges_in_new(prev: str, new: str) -> list[tuple[int, int]]:
    """Return merged [start, end) ranges in `new` that differ from `prev` (best-effort)."""
    sm = SequenceMatcher(a=prev, b=new, autojunk=False)
    ranges: list[tuple[int, int]] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        if j1 < j2:
            ranges.append((j1, j2))
    return _merge_ranges(ranges)


def _merge_ranges(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    if not ranges:
        return []
    ranges = sorted(ranges)
    out = [ranges[0]]
    for start, end in ranges[1:]:
        ps, pe = out[-1]
        if start <= pe:
            out[-1] = (ps, max(pe, end))
        else:
            out.append((start, end))
    return out


def chunk_ids_intersecting_ranges(
    chunks: list[dict],
    ranges: list[tuple[int, int]],
) -> set[str]:
    """chunks items must have start_char, end_char, id (or chunk_business_id)."""
    dirty: set[str] = set()
    for ch in chunks:
        s = int(ch.get("start_char", 0))
        e = int(ch.get("end_char", 0))
        cid = ch.get("id") or ch.get("chunk_business_id") or ""
        for rs, re in ranges:
            if s < re and e > rs:
                dirty.add(str(cid))
                break
    return dirty
