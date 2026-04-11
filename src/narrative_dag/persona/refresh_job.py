"""Async persona_refresh job: compose snapshot after analyze."""

from __future__ import annotations

import json
import os
import threading
from typing import Any

from langchain_core.messages import HumanMessage

from narrative_dag.db import init_db
from narrative_dag.llm import build_run_llm_bundle, resolve_run_llm_provider, structured_invoke
from narrative_dag.persona.engine import (
    analyzed_word_count_from_chunks,
    build_deterministic_persona,
    build_pet_style_policy,
    build_timbre_delta,
    compute_input_hash,
    should_materialize_persona,
)
from narrative_dag.pet_soul import load_pet_soul_markdown
from narrative_dag.schemas import DocumentState, InkblotPersonaLLMSnapshot
from narrative_dag.store.job_store import JobStore
from narrative_dag.store.persona_store import PersonaStore
from narrative_dag.store.run_store import RunStore


def schedule_persona_refresh_after_analyze(
    db_path: str,
    *,
    document_id: str,
    revision_id: str | None,
    run_id: str,
    provider: str | None = None,
) -> None:
    """Enqueue persona_refresh once per successful analyze; runs in a daemon thread."""
    if os.getenv("EDITR_DISABLE_PERSONA_REFRESH", "").strip().lower() in ("1", "true", "yes"):
        return
    if not revision_id:
        return
    job_id: str | None = None
    conn = init_db(db_path)
    try:
        js = JobStore(conn)
        if js.find_succeeded_persona_job(document_id, revision_id, run_id):
            return
        if js.find_active_persona_job_for_run(document_id, revision_id, run_id):
            return
        job_id = js.create_job(
            "persona_refresh",
            document_id=document_id,
            revision_id=revision_id,
            run_id=run_id,
            payload={"document_id": document_id, "revision_id": revision_id, "run_id": run_id, "provider": provider},
        )
    finally:
        conn.close()
    if not job_id:
        return

    def _run() -> None:
        try:
            run_persona_refresh_job(db_path, job_id)
        except Exception:
            pass

    threading.Thread(target=_run, daemon=True).start()


def run_persona_refresh_job(db_path: str, job_id: str) -> None:
    conn = init_db(db_path)
    try:
        _run_persona_refresh_job_impl(conn, job_id)
    finally:
        conn.close()


def _run_persona_refresh_job_impl(conn: Any, job_id: str) -> None:
    js = JobStore(conn)
    job = js.get_job(job_id)
    if not job or job.get("kind") != "persona_refresh":
        return
    payload = job.get("payload") or {}
    document_id = str(payload.get("document_id") or job.get("document_id") or "")
    revision_id = payload.get("revision_id") or job.get("revision_id")
    run_id = str(payload.get("run_id") or job.get("run_id") or "")
    provider = payload.get("provider")
    if not document_id or not run_id or not revision_id:
        js.update_job(job_id, "failed", error="missing document_id/revision_id/run_id")
        return

    if js.find_succeeded_persona_job(document_id, str(revision_id), run_id):
        js.update_job(
            job_id,
            "succeeded",
            result={"skipped": True, "reason": "already_succeeded"},
            run_id=run_id,
        )
        return

    try:
        js.update_job(job_id, "running", run_id=run_id)
        rs = RunStore(conn)
        ps = PersonaStore(conn)
        ds_state = rs.get_document_state(run_id)
        if not ds_state:
            js.update_job(job_id, "failed", error="no document_state for run", run_id=run_id)
            return
        if not isinstance(ds_state, DocumentState):
            ds_state = DocumentState.model_validate(ds_state)

        chunks_meta = rs.list_chunks_for_run(run_id)
        artifacts: list[dict[str, Any]] = []
        for row in chunks_meta:
            art = rs.get_chunk_artifact(run_id, row["chunk_id"])
            if art:
                artifacts.append(art)
        analyzed_words = analyzed_word_count_from_chunks(artifacts)
        chunk_count = len(chunks_meta)

        soul = load_pet_soul_markdown(document_id)
        soul_md = soul["markdown"]
        soul_hash = soul["hash"]
        soul_path = soul["primary_path"]

        genre = None
        if ds_state.genre_intention and hasattr(ds_state.genre_intention, "genre"):
            genre = ds_state.genre_intention.genre

        det = build_deterministic_persona(
            document_id=document_id,
            revision_id=str(revision_id),
            run_id=run_id,
            document_state=ds_state,
            genre=genre,
            analyzed_words=analyzed_words,
            chunk_count=chunk_count,
            soul_markdown=soul_md,
        )
        state_flag = str(det.get("state") or "bootstrap")

        prev = ps.get_latest_snapshot(document_id)
        prev_policy = prev.get("pet_style_policy_json") if prev else None
        policy = build_pet_style_policy(ds_state, prior=prev_policy if isinstance(prev_policy, dict) else None)

        ds_json = json.dumps(ds_state.model_dump(mode="json"), sort_keys=True)
        ihash = compute_input_hash(document_id, str(revision_id), run_id, ds_json)
        if prev and prev.get("input_hash") == ihash:
            js.update_job(
                job_id,
                "succeeded",
                result={"skipped": True, "reason": "unchanged_input_hash", "persona_version": prev.get("version")},
                run_id=run_id,
                input_hash=ihash,
                output_persona_version=prev.get("version"),
            )
            return

        llm_snap: dict[str, Any] | None = None
        if should_materialize_persona(analyzed_words=analyzed_words, chunk_count=chunk_count):
            bundle = build_run_llm_bundle(resolve_run_llm_provider(provider))
            llm = bundle.llm_chat
            prompt = f"""Given this story persona bundle (JSON), produce a compact companion alignment AND a visual_model for a small UI avatar.

Requirements for visual_model:
- svg_path_d: ONE valid SVG path "d" string only (no XML tags). Use viewBox coordinates 0–100; center roughly at (50,50). Symmetric Rorschach-style blob is ideal: one closed path, organic curves.
- Shape mood from genre/tone: horror/thriller → slightly jagged or spiky; romance/literary → softer rounded; comedy → playful asymmetry allowed.
- primary_color and secondary_color: hex #RRGGBB only; pair should feel cohesive with the story mood (muted for grim, warmer for gentle).
- animation_speed: float 0.25–3.0; higher for tense/anxious stories, lower for calm/contemplative.

Also fill one_liner, alignment_notes, tone_reminders as before.

Additionally, write personality_paragraph: exactly two or three sentences describing how Inkblot should sound and relate to this specific story (voice, stance toward the writer, emotional temperature). Advisory only; do not claim facts not supported by the bundle.

Persona bundle (JSON):
{json.dumps(det)[:8000]}
"""
            snap = structured_invoke(
                llm,
                [HumanMessage(content=prompt)],
                InkblotPersonaLLMSnapshot,
                trace_label="persona_snapshot",
            )
            llm_snap = snap.model_dump(mode="json")

        version = ps.next_version(document_id)
        timbre_delta = build_timbre_delta(prev, policy)

        row_id = ps.insert_snapshot(
            document_id,
            revision_id=str(revision_id),
            version=version,
            state=state_flag,
            deterministic=det,
            llm_snapshot=llm_snap,
            pet_style_policy=policy,
            soul_seed_path=soul_path or None,
            soul_seed_hash=soul_hash or None,
            source_run_id=run_id,
            timbre_delta=timbre_delta,
            input_hash=ihash,
        )
        ps.append_event(
            document_id,
            "persona_refresh",
            "analyze_run",
            source_id=run_id,
            revision_id=str(revision_id),
            payload={"persona_row_id": row_id, "version": version},
        )
        js.update_job(
            job_id,
            "succeeded",
            result={
                "persona_version": version,
                "document_id": document_id,
                "revision_id": revision_id,
                "run_id": run_id,
            },
            run_id=run_id,
            input_hash=ihash,
            output_persona_version=version,
        )
    except Exception as e:
        js.update_job(job_id, "failed", error=str(e), run_id=run_id)
