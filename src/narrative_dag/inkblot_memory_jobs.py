"""Async jobs: Inkblot document memory batch merge, close summary, persona paragraph digest."""

from __future__ import annotations

import json
import os
import threading
from typing import Any

from langchain_core.messages import HumanMessage

import narrative_dag.config as config_module
from narrative_dag.db import init_db
from narrative_dag.llm import build_run_llm_bundle, resolve_run_llm_provider, structured_invoke
from narrative_dag.persona.engine import (
    analyzed_word_count_from_chunks,
    build_deterministic_persona,
    build_pet_style_policy,
    build_timbre_delta,
    compute_input_hash,
)
from narrative_dag.pet_soul import load_pet_soul_markdown
from narrative_dag.prompts.inkblot_memory import (
    inkblot_memory_batch_prompt,
    inkblot_memory_close_prompt,
    inkblot_persona_digest_prompt,
)
from narrative_dag.schemas import (
    DocumentState,
    InkblotMemoryCloseSummary,
    InkblotMemoryMergeResult,
    InkblotPersonaLLMSnapshot,
    InkblotPersonaParagraphRefresh,
)
from narrative_dag.store.inkblot_memory_store import InkblotMemoryStore
from narrative_dag.store.job_store import JobStore
from narrative_dag.store.persona_store import PersonaStore
from narrative_dag.store.run_store import RunStore
from narrative_dag.store.story_chat_store import StoryChatStore


def _disabled() -> bool:
    return os.getenv("EDITR_DISABLE_INKBLOT_MEMORY_JOBS", "").strip().lower() in ("1", "true", "yes")


def _inline_jobs() -> bool:
    """Run Inkblot memory jobs on the caller thread (tests / Windows SQLite teardown)."""
    return os.getenv("EDITR_INKBLOT_MEMORY_JOBS_INLINE", "").strip().lower() in ("1", "true", "yes")


def is_quick_coach_manifest(manifest: dict[str, Any] | None) -> bool:
    return (manifest or {}).get("source") == "quick_coach"


def count_inkblot_user_turns(turns: list[dict[str, Any]]) -> int:
    n = 0
    for t in turns:
        if t.get("role") != "user":
            continue
        if is_quick_coach_manifest(t.get("context_manifest")):
            continue
        n += 1
    return n


def format_transcript(turns: list[dict[str, Any]], max_chars: int) -> tuple[str, bool]:
    lines: list[str] = []
    for t in turns:
        role = str(t.get("role") or "")
        content = str(t.get("content") or "")
        lines.append(f"{role}: {content}")
    s = "\n\n".join(lines)
    if len(s) <= max_chars:
        return s, False
    return s[-max_chars:], True


def transcript_tail_for_last_k_inkblot_users(
    turns: list[dict[str, Any]], k: int, max_chars: int
) -> tuple[str, bool]:
    """Take turns starting at the k-th-from-last inkblot user message (inclusive)."""
    idxs: list[int] = []
    for i, t in enumerate(turns):
        if t.get("role") != "user":
            continue
        if is_quick_coach_manifest(t.get("context_manifest")):
            continue
        idxs.append(i)
    if not idxs:
        return "", False
    take_from = idxs[-k] if len(idxs) >= k else idxs[0]
    segment = turns[take_from:]
    return format_transcript(segment, max_chars)


def schedule_inkblot_followup_jobs(
    db_path: str,
    *,
    document_id: str,
    session_id: str,
    provider: str | None,
) -> None:
    """After a successful story-chat turn, enqueue memory batch / persona digest when thresholds hit."""
    if _disabled():
        return
    try:
        conn = init_db(db_path)
        try:
            sc = StoryChatStore(conn)
            turns = sc.list_turns(session_id)
            n = count_inkblot_user_turns(turns)
            batch_n = config_module.INKBLOT_MEMORY_BATCH_USER_TURNS
            digest_n = config_module.INKBLOT_PERSONA_DIGEST_USER_TURNS
            js = JobStore(conn)

            if n > 0 and batch_n > 0 and n % batch_n == 0:
                dedupe = f"mem_batch:{session_id}:{n}"
                if not _has_active_dedupe(conn, "inkblot_memory_batch", document_id, dedupe):
                    jid = js.create_job(
                        "inkblot_memory_batch",
                        document_id=document_id,
                        run_id=None,
                        payload={
                            "document_id": document_id,
                            "session_id": session_id,
                            "trigger_inkblot_user_count": n,
                            "dedupe_key": dedupe,
                            "provider": provider,
                        },
                    )

                    if _inline_jobs():
                        run_inkblot_memory_batch_job(db_path, jid)
                    else:
                        threading.Thread(
                            target=lambda j=jid: run_inkblot_memory_batch_job(db_path, j),
                            daemon=True,
                        ).start()

            if n > 0 and digest_n > 0 and n % digest_n == 0:
                dedupe = f"persona_digest:{session_id}:{n}"
                if not _has_active_dedupe(conn, "inkblot_persona_digest", document_id, dedupe):
                    jid = js.create_job(
                        "inkblot_persona_digest",
                        document_id=document_id,
                        run_id=None,
                        payload={
                            "document_id": document_id,
                            "session_id": session_id,
                            "trigger_inkblot_user_count": n,
                            "dedupe_key": dedupe,
                            "provider": provider,
                        },
                    )

                    if _inline_jobs():
                        run_inkblot_persona_digest_job(db_path, jid)
                    else:
                        threading.Thread(
                            target=lambda j=jid: run_inkblot_persona_digest_job(db_path, j),
                            daemon=True,
                        ).start()
        finally:
            conn.close()
    except Exception:
        pass


def _has_active_dedupe(conn: Any, kind: str, document_id: str, dedupe_key: str) -> bool:
    cur = conn.cursor()
    needle = f'%"dedupe_key":"{dedupe_key}"%'
    cur.execute(
        """
        SELECT 1 FROM async_jobs WHERE kind = ? AND document_id = ?
        AND status IN ('queued', 'running') AND payload_json LIKE ?
        LIMIT 1
        """,
        (kind, document_id, needle),
    )
    return cur.fetchone() is not None


def run_inkblot_memory_batch_job(db_path: str, job_id: str) -> None:
    conn = init_db(db_path)
    try:
        _run_inkblot_memory_batch_impl(conn, job_id)
    finally:
        conn.close()


def _run_inkblot_memory_batch_impl(conn: Any, job_id: str) -> None:
    js = JobStore(conn)
    job = js.get_job(job_id)
    if not job or job.get("kind") != "inkblot_memory_batch":
        return
    payload = job.get("payload") or {}
    document_id = str(payload.get("document_id") or "")
    session_id = str(payload.get("session_id") or "")
    provider = payload.get("provider")
    if not document_id or not session_id:
        js.update_job(job_id, "failed", error="missing document_id/session_id")
        return
    try:
        js.update_job(job_id, "running")
        sc = StoryChatStore(conn)
        ms = InkblotMemoryStore(conn)
        turns = sc.list_turns(session_id)
        k = config_module.INKBLOT_MEMORY_BATCH_USER_TURNS
        seg, trunc = transcript_tail_for_last_k_inkblot_users(
            turns,
            k,
            config_module.INKBLOT_MEMORY_TRANSCRIPT_MAX_CHARS,
        )
        existing = json.dumps(ms.get_payload(document_id), sort_keys=True)
        prompt = inkblot_memory_batch_prompt(
            existing_memory_json=existing,
            transcript_segment=seg,
            truncated=trunc,
        )
        bundle = build_run_llm_bundle(resolve_run_llm_provider(provider))
        llm = bundle.llm_chat
        merged = structured_invoke(
            llm,
            [HumanMessage(content=prompt)],
            InkblotMemoryMergeResult,
            trace_label="inkblot_memory_batch",
        )
        patch = merged.model_dump(mode="json")
        patch["last_batch_kind"] = "incremental"
        patch["last_batch_session_id"] = session_id
        base = ms.get_payload(document_id)
        merged_payload = {**base, **patch, "schema_version": patch.get("schema_version", 1)}
        ms.upsert_payload(document_id, merged_payload)
        js.update_job(
            job_id,
            "succeeded",
            result={"document_id": document_id, "session_id": session_id},
        )
    except Exception as e:
        js.update_job(job_id, "failed", error=str(e))


def run_inkblot_memory_close_job(db_path: str, job_id: str) -> None:
    conn = init_db(db_path)
    try:
        _run_inkblot_memory_close_impl(conn, job_id)
    finally:
        conn.close()


def _run_inkblot_memory_close_impl(conn: Any, job_id: str) -> None:
    js = JobStore(conn)
    job = js.get_job(job_id)
    if not job or job.get("kind") != "inkblot_memory_close":
        return
    payload = job.get("payload") or {}
    document_id = str(payload.get("document_id") or "")
    session_id = str(payload.get("session_id") or "")
    provider = payload.get("provider")
    last_turn_index = payload.get("last_turn_index")
    if not document_id or not session_id:
        js.update_job(job_id, "failed", error="missing document_id/session_id")
        return
    try:
        js.update_job(job_id, "running")
        sc = StoryChatStore(conn)
        ms = InkblotMemoryStore(conn)
        sess = sc.get_session(session_id)
        if not sess or sess.get("document_id") != document_id:
            js.update_job(job_id, "failed", error="invalid session")
            return
        turns = sc.list_turns(session_id)
        if last_turn_index is not None:
            try:
                li = int(last_turn_index)
                turns = [t for t in turns if int(t.get("turn_index", -1)) <= li]
            except (TypeError, ValueError):
                pass
        full_text, trunc = format_transcript(turns, config_module.INKBLOT_MEMORY_TRANSCRIPT_MAX_CHARS)
        if not full_text.strip():
            js.update_job(job_id, "succeeded", result={"skipped": True, "reason": "empty_transcript"})
            return
        prompt = inkblot_memory_close_prompt(transcript=full_text, truncated=trunc)
        bundle = build_run_llm_bundle(resolve_run_llm_provider(provider))
        llm = bundle.llm_chat
        out = structured_invoke(
            llm,
            [HumanMessage(content=prompt)],
            InkblotMemoryCloseSummary,
            trace_label="inkblot_memory_close",
        )
        od = out.model_dump(mode="json")
        base = ms.get_payload(document_id)
        from datetime import datetime, timezone

        close_patch = {
            "last_close_session_id": session_id,
            "last_session_point": od.get("session_point", ""),
            "last_session_goals": od.get("session_goals", []),
            "last_session_emotions": od.get("session_emotions", []),
            "last_close_at": datetime.now(timezone.utc).isoformat(),
        }
        merged_payload = {**base, **close_patch, "schema_version": max(int(base.get("schema_version", 1)), int(od.get("schema_version", 1)))}
        ms.upsert_payload(document_id, merged_payload)
        js.update_job(job_id, "succeeded", result={"document_id": document_id, "session_id": session_id})
    except Exception as e:
        js.update_job(job_id, "failed", error=str(e))


def schedule_inkblot_memory_close(
    db_path: str,
    *,
    document_id: str,
    session_id: str,
    last_turn_index: int | None,
    provider: str | None,
) -> bool:
    """Create close-summary job synchronously; run LLM work in a background thread."""
    if _disabled():
        return False
    try:
        conn = init_db(db_path)
        try:
            js = JobStore(conn)
            dedupe = f"close:{session_id}:{last_turn_index if last_turn_index is not None else 'all'}"
            if _has_active_dedupe(conn, "inkblot_memory_close", document_id, dedupe):
                return False
            jid = js.create_job(
                "inkblot_memory_close",
                document_id=document_id,
                run_id=None,
                payload={
                    "document_id": document_id,
                    "session_id": session_id,
                    "last_turn_index": last_turn_index,
                    "dedupe_key": dedupe,
                    "provider": provider,
                },
            )
        finally:
            conn.close()
    except Exception:
        return False

    if _inline_jobs():
        run_inkblot_memory_close_job(db_path, jid)
    else:
        threading.Thread(
            target=lambda j=jid: run_inkblot_memory_close_job(db_path, j),
            daemon=True,
        ).start()
    return True


def run_inkblot_persona_digest_job(db_path: str, job_id: str) -> None:
    conn = init_db(db_path)
    try:
        _run_inkblot_persona_digest_impl(conn, job_id)
    finally:
        conn.close()


def _run_inkblot_persona_digest_impl(conn: Any, job_id: str) -> None:
    js = JobStore(conn)
    job = js.get_job(job_id)
    if not job or job.get("kind") != "inkblot_persona_digest":
        return
    payload = job.get("payload") or {}
    document_id = str(payload.get("document_id") or "")
    provider = payload.get("provider")
    if not document_id:
        js.update_job(job_id, "failed", error="missing document_id")
        return
    try:
        js.update_job(job_id, "running")
        rs = RunStore(conn)
        ps = PersonaStore(conn)
        ms = InkblotMemoryStore(conn)

        run_id = rs.find_latest_run_for_document_with_story_map(document_id)
        if not run_id:
            run_id = rs.find_latest_run_for_document(document_id)
        if not run_id:
            js.update_job(job_id, "failed", error="no run for document")
            return

        ds_state = rs.get_document_state(run_id)
        if not ds_state:
            js.update_job(job_id, "failed", error="no document_state")
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
        soul_path = soul["primary_path"]
        soul_hash = soul["hash"]

        genre = None
        if ds_state.genre_intention and hasattr(ds_state.genre_intention, "genre"):
            genre = ds_state.genre_intention.genre

        cur = conn.cursor()
        cur.execute("SELECT revision_id FROM runs WHERE run_id = ? LIMIT 1", (run_id,))
        r = cur.fetchone()
        revision_id = str(r[0]) if r and r[0] else None

        det = build_deterministic_persona(
            document_id=document_id,
            revision_id=revision_id,
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

        memory_payload = ms.get_payload(document_id)
        prior_llm = (prev or {}).get("llm_snapshot_json") if prev else None
        if not isinstance(prior_llm, dict):
            prior_llm = {}
        prior_para = str(prior_llm.get("personality_paragraph") or "")

        bundle = build_run_llm_bundle(resolve_run_llm_provider(provider))
        llm = bundle.llm_chat
        prompt = inkblot_persona_digest_prompt(
            deterministic_json=json.dumps(det),
            memory_json=json.dumps(memory_payload),
            prior_paragraph=prior_para,
        )
        para = structured_invoke(
            llm,
            [HumanMessage(content=prompt)],
            InkblotPersonaParagraphRefresh,
            trace_label="inkblot_persona_digest",
        )
        merged_snap = {**prior_llm, **para.model_dump(mode="json")}
        validated = InkblotPersonaLLMSnapshot.model_validate(merged_snap)
        llm_snap_merged = validated.model_dump(mode="json")

        ds_json = json.dumps(ds_state.model_dump(mode="json"), sort_keys=True)
        ihash = compute_input_hash(document_id, revision_id or "", run_id, ds_json)

        version = ps.next_version(document_id)
        timbre_delta = build_timbre_delta(prev, policy)

        ps.insert_snapshot(
            document_id,
            revision_id=revision_id,
            version=version,
            state=state_flag,
            deterministic=det,
            llm_snapshot=llm_snap_merged,
            pet_style_policy=policy,
            soul_seed_path=soul_path or None,
            soul_seed_hash=soul_hash or None,
            source_run_id=run_id,
            timbre_delta=timbre_delta,
            input_hash=ihash,
        )
        ps.append_event(
            document_id,
            "inkblot_persona_digest",
            "job",
            source_id=job_id,
            revision_id=revision_id,
            payload={"run_id": run_id, "version": version},
        )
        js.update_job(
            job_id,
            "succeeded",
            result={"persona_version": version, "document_id": document_id},
            output_persona_version=version,
            input_hash=ihash,
        )
    except Exception as e:
        js.update_job(job_id, "failed", error=str(e))


def run_pending_inkblot_job_for_tests(db_path: str, kind: str) -> bool:
    """Process one queued job of kind (for tests). Returns True if a job ran."""
    conn = init_db(db_path)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT job_id FROM async_jobs WHERE kind = ? AND status = 'queued' ORDER BY created_at ASC LIMIT 1",
            (kind,),
        )
        row = cur.fetchone()
        if not row:
            return False
        job_id = str(row[0])
        if kind == "inkblot_memory_batch":
            run_inkblot_memory_batch_job(db_path, job_id)
        elif kind == "inkblot_persona_digest":
            run_inkblot_persona_digest_job(db_path, job_id)
        elif kind == "inkblot_memory_close":
            run_inkblot_memory_close_job(db_path, job_id)
        else:
            return False
        return True
    finally:
        conn.close()
