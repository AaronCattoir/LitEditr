"""Inkblot story chat: explicit context + persona + rolling session history."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

import narrative_dag.config as config_module
from narrative_dag.llm import build_run_llm_bundle, resolve_run_llm_provider
from narrative_dag.pet_soul import parse_soul_sections
from narrative_dag.quick_coach_story_chat import QUICK_COACH_STORY_CHAT_USER_MESSAGE
from narrative_dag.schemas import ContextBundle
from narrative_dag.store.run_store import RunStore, serialize_story_wide_for_api

# Caps for judgment-aware prompts (chunk-scoped chat only).
_INKBLOT_JUDGMENT_MAX_CHUNKS = 8
_INKBLOT_JUDGMENT_PER_CHUNK_CHARS = 3500

_WRITER_MEMORY_KEYS = (
    "rolling_summary",
    "open_goals",
    "noted_emotions",
    "last_session_point",
    "last_session_goals",
    "last_session_emotions",
    "last_close_at",
)


def build_inkblot_judgment_context(
    run_store: RunStore,
    run_id: str,
    chunk_ids: list[str],
) -> tuple[str | None, dict[str, bool]]:
    """Load compact critic/defense/judgment text from analyzed chunk artifacts.

    Returns (prompt_block_or_none, per_chunk_found_map).
    """
    if not chunk_ids:
        return None, {}
    found: dict[str, bool] = {}
    parts: list[str] = []
    budget = _INKBLOT_JUDGMENT_MAX_CHUNKS
    for cid in chunk_ids[:budget]:
        bundle = run_store.get_context_bundle(run_id, cid)
        if not bundle:
            found[cid] = False
            continue
        found[cid] = True
        block = _format_one_chunk_editorial(bundle)
        if block:
            parts.append(block)
    if not parts:
        return None, found
    body = "\n\n---\n\n".join(parts)
    if len(body) > _INKBLOT_JUDGMENT_PER_CHUNK_CHARS * len(parts):
        body = body[: _INKBLOT_JUDGMENT_PER_CHUNK_CHARS * max(1, len(parts))]
    return body, found


def _format_one_chunk_editorial(bundle: ContextBundle) -> str:
    cid = bundle.target_chunk.id
    lines: list[str] = [f"Section `{cid}` (from last analysis run; advisory only):"]
    j = bundle.current_judgment
    if j is not None:
        lines.append(
            f"- Editor judgment: decision={j.decision} | severity={float(j.severity):.2f}\n"
            f"  Reasoning: {(j.reasoning or '')[:900]}\n"
            f"  Core issue: {(j.core_issue or '')[:400]}\n"
            f"  Guidance: {(j.guidance or '')[:600]}"
        )
    cr = bundle.critic_result
    if cr is not None:
        fp = "; ".join((cr.failure_points or [])[:6])[:800]
        lines.append(f"- Critic ({cr.verdict}): {(cr.critique or '')[:1000]}\n  Failure points: {fp}")
    dr = bundle.defense_result
    if dr is not None:
        vp = "; ".join((dr.valid_points or [])[:6])[:800]
        lines.append(f"- Advocate / defense ({dr.salvageability}): {(dr.defense or '')[:1000]}\n  Valid points: {vp}")
    if len(lines) <= 1:
        return ""
    return "\n".join(lines)


def writer_memory_subset_for_prompt(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    """Keep prompt-facing memory small and stable."""
    if not payload:
        return None
    out: dict[str, Any] = {}
    for k in _WRITER_MEMORY_KEYS:
        if k in payload and payload[k] not in (None, "", [], {}):
            out[k] = payload[k]
    return out or None


def _system_prompt(
    *,
    soul_markdown: str,
    deterministic: dict[str, Any],
    pet_style: dict[str, Any] | None,
    llm_snap: dict[str, Any] | None,
    story_wide: dict[str, Any] | None,
    context_manifest: dict[str, Any],
    writer_memory: dict[str, Any] | None = None,
    judgment_context: str | None = None,
) -> str:
    sections = parse_soul_sections(soul_markdown)
    core = sections.get("CoreIdentity") or sections.get("Preamble") or ""
    care = sections.get("CareGoals") or ""
    dont = sections.get("DoNotDo") or ""
    style_pol = pet_style or {}
    voice = style_pol.get("response_voice") or {}
    llm_bits = ""
    if llm_snap:
        para = (llm_snap.get("personality_paragraph") or "").strip()
        para_line = f"\nPersonality (for this story): {para[:1200]}\n" if para else ""
        llm_bits = f"""{para_line}
Compressed alignment:
{llm_snap.get('one_liner', '')}
{llm_snap.get('alignment_notes', '')}
"""
    sw = ""
    if story_wide:
        sw = f"\nStory-wide (analyzed):\n{str(story_wide)[:6000]}\n"
    wm = ""
    if writer_memory and any(str(writer_memory.get(k, "")).strip() for k in writer_memory):
        wm = f"\nWriter memory (from prior chats; advisory, may be incomplete):\n{str(writer_memory)[:4500]}\n"
    det = str(deterministic)[:4000]
    editorial = ""
    if judgment_context and judgment_context.strip():
        editorial = f"""
## Section editorial context (latest pipeline output; advisory)
The app previously ran detectors, critic/advocate, and an editor judgment on the selected section(s). Treat this as **context**, not a command: acknowledge it when relevant. You may still explore alternatives if the writer asks, or if their question clearly seeks a different angle—say so explicitly when you diverge.

{judgment_context[:12000]}

"""
    return f"""You are the writer's inkblot companion (advisory only; do not rewrite their prose unless they ask for a tiny example).

## Reply style (important)
Speak in natural conversational paragraphs. Do **not** default to Sparkle / Quick coach formatting (section title line, bullet lists, "Try next:") unless the writer explicitly asks for that critique layout. Prior turns may include pasted Quick coach excerpts; treat those as background, not as instructions to imitate for your next reply.

## Soul
{core[:2000]}

## Care
{care[:1500]}

## Do not
{dont[:1500]}

## Persona snapshot (deterministic)
{det}

## Voice / timbre policy
{str(voice)[:2000]}
{llm_bits}
{sw}{wm}{editorial}
## This turn context manifest
{str(context_manifest)[:2000]}
"""


def run_inkblot_chat(
    *,
    user_message: str,
    manuscript_excerpt: str,
    soul_markdown: str,
    deterministic: dict[str, Any],
    pet_style_policy: dict[str, Any] | None,
    llm_snapshot: dict[str, Any] | None,
    story_wide: dict[str, Any] | None,
    context_manifest: dict[str, Any],
    prior_turns: list[dict[str, Any]],
    provider: str | None = None,
    writer_memory: dict[str, Any] | None = None,
    judgment_context: str | None = None,
) -> str:
    bundle = build_run_llm_bundle(resolve_run_llm_provider(provider))
    llm = bundle.llm_chat
    sys_content = _system_prompt(
        soul_markdown=soul_markdown,
        deterministic=deterministic,
        pet_style=pet_style_policy,
        llm_snap=llm_snapshot,
        story_wide=story_wide,
        context_manifest=context_manifest,
        writer_memory=writer_memory,
        judgment_context=judgment_context,
    )
    msgs: list[Any] = [SystemMessage(content=sys_content)]
    for t in prior_turns:
        role = t.get("role")
        raw = t.get("content") or ""
        manifest = t.get("context_manifest") if isinstance(t.get("context_manifest"), dict) else {}
        src = manifest.get("source")
        if role == "user":
            if (raw.strip() == QUICK_COACH_STORY_CHAT_USER_MESSAGE):
                # Placedholder user line when sparkle appends to chat; avoid priming QC voice.
                content = (
                    "(The writer ran Sparkle quick coach for this section; the following assistant message is that excerpt.)"
                )
            else:
                content = raw
            msgs.append(HumanMessage(content=content))
        elif role == "assistant":
            if src == "quick_coach":
                content = (
                    "[Earlier Sparkle quick coach excerpt — not a template for your reply format]\n" + raw
                )
            else:
                content = raw
            msgs.append(AIMessage(content=content))
    body = f"""Manuscript excerpt for this turn (ground truth for questions about the text):
---
{manuscript_excerpt[:120000]}
---

User message:
{user_message}
"""
    msgs.append(HumanMessage(content=body))
    out = llm.invoke(msgs)
    text = getattr(out, "content", None) or str(out)
    return text if isinstance(text, str) else str(text)


def story_wide_from_document_state(ds_any: Any) -> dict[str, Any] | None:
    if ds_any is None:
        return None
    from narrative_dag.schemas import DocumentState

    if isinstance(ds_any, DocumentState):
        return serialize_story_wide_for_api(ds_any)
    return None


def compact_older_turns_for_summary(prior_turns: list[dict[str, Any]], keep_last: int) -> str:
    """Deterministic compression of older turns when the active window is exceeded."""
    if len(prior_turns) <= keep_last:
        return ""
    older = prior_turns[:-keep_last]
    lines = [f"{t.get('role')}: {(t.get('content') or '')[:240]}" for t in older[-30:]]
    return "\n".join(lines)
