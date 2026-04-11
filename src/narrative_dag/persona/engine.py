"""Deterministic persona composition, timbre, and thresholds."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import narrative_dag.config as config_module
from narrative_dag.pet_soul import load_pet_soul_markdown, parse_soul_sections
from narrative_dag.schemas import DocumentState


def count_words(text: str) -> int:
    return len([w for w in (text or "").split() if w.strip()])


def analyzed_word_count_from_chunks(chunks: list[dict[str, Any]]) -> int:
    """Sum word counts from chunk artifacts' target_chunk.text if present."""
    total = 0
    for a in chunks:
        tc = a.get("target_chunk") or {}
        if isinstance(tc, dict) and isinstance(tc.get("text"), str):
            total += count_words(tc["text"])
    return total


def should_materialize_persona(*, analyzed_words: int, chunk_count: int) -> bool:
    return analyzed_words >= config_module.PERSONA_MIN_ANALYZED_WORDS or chunk_count >= config_module.PERSONA_MIN_ANALYZED_CHUNKS


def compute_input_hash(
    document_id: str,
    revision_id: str | None,
    run_id: str,
    document_state_json: str,
) -> str:
    raw = f"{document_id}|{revision_id or ''}|{run_id}|{document_state_json}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_pet_style_policy(ds: DocumentState, *, prior: dict[str, Any] | None = None) -> dict[str, Any]:
    """Derive voice/timbre policy from voice_baseline and narrative signals."""
    vb = ds.voice_baseline
    if hasattr(vb, "model_dump"):
        vb_dict = vb.model_dump(mode="json")
    elif isinstance(vb, dict):
        vb_dict = vb
    else:
        vb_dict = {}
    layers = ("lexical", "syntactic", "rhetorical", "psychological")
    summaries = []
    for L in layers:
        layer = vb_dict.get(L) or {}
        if isinstance(layer, dict) and (layer.get("summary") or "").strip():
            summaries.append(str(layer["summary"]).strip())
    voice_summary = " ".join(summaries[:4])[:1200]

    emo = ds.emotional_curve or []
    last_reg = ""
    if emo:
        last = emo[-1]
        if isinstance(last, dict):
            last_reg = str(last.get("register") or "")

    prior = prior or {}
    alpha = 0.35
    merged_voice = voice_summary
    if prior.get("response_voice", {}).get("summary"):
        merged_voice = f"{prior['response_voice']['summary']}\n{voice_summary}".strip()[:2000]

    return {
        "response_voice": {
            "summary": merged_voice,
            "temperature": "match_story" if voice_summary else "neutral",
        },
        "forbidden_style_drifts": [
            "mocking_the_writer",
            "cosmic_horror_tone_in_slice_of_life_without_evidence",
        ],
        "intensity_bounds": {
            "max_playfulness": 0.85 if "playful" in (last_reg or "").lower() else 0.55,
            "min_seriousness": 0.35,
        },
        "source": {"voice_layers": vb_dict, "last_emotional_register": last_reg},
        "_alpha_smoothing": alpha,
    }


def build_deterministic_persona(
    *,
    document_id: str,
    revision_id: str | None,
    run_id: str,
    document_state: DocumentState,
    genre: str | None,
    analyzed_words: int,
    chunk_count: int,
    soul_markdown: str,
) -> dict[str, Any]:
    po = document_state.plot_overview
    plot_bits = []
    if po:
        if po.story_point:
            plot_bits.append(po.story_point.strip())
        if po.plot_summary:
            plot_bits.append(po.plot_summary.strip())
    cast = []
    cdb = document_state.character_database
    if cdb and cdb.characters:
        for c in cdb.characters[:12]:
            if c.canonical_name:
                cast.append(c.canonical_name)

    sections = parse_soul_sections(soul_markdown)
    state = "bootstrap"
    if should_materialize_persona(analyzed_words=analyzed_words, chunk_count=chunk_count):
        state = "active"

    return {
        "document_id": document_id,
        "revision_id": revision_id,
        "source_run_id": run_id,
        "state": state,
        "genre": genre or "",
        "analyzed_word_estimate": analyzed_words,
        "chunk_count": chunk_count,
        "plot_blurb": "\n\n".join(plot_bits)[:4000],
        "cast_names": cast,
        "soul_sections": {k: v[:2000] for k, v in list(sections.items())[:12]},
        "narrative_map_len": len(document_state.narrative_map or []),
        "emotional_curve_len": len(document_state.emotional_curve or []),
    }


def build_timbre_delta(
    prev_snapshot: dict[str, Any] | None,
    new_policy: dict[str, Any],
) -> dict[str, Any]:
    """Human-readable delta stub for observability."""
    if not prev_snapshot:
        return {"kind": "initial", "note": "first persona snapshot"}
    prev = (prev_snapshot.get("pet_style_policy_json") or {}) if isinstance(prev_snapshot, dict) else {}
    prev_s = ""
    if isinstance(prev, dict):
        rv = prev.get("response_voice") or {}
        prev_s = str(rv.get("summary") or "")[:200]
    new_s = str((new_policy.get("response_voice") or {}).get("summary") or "")[:200]
    return {"kind": "update", "prev_voice_preview": prev_s, "new_voice_preview": new_s}
