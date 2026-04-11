"""Transport-agnostic application service: single entrypoint for CLI, API, and future GUI."""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from typing import Any

import narrative_dag.config as config_module
from narrative_dag.db import init_db
from narrative_dag.store.job_store import JobStore
from narrative_dag.contracts import (
    AnalyzeDocumentRequest,
    AnalyzeDocumentResponse,
    ChatRequest,
    ChatResponse,
    QuickCoachResponse,
    StoryChatRequest,
    StoryChatResponse,
    StoryChatSessionCloseRequest,
    StoryChatSessionCloseResponse,
    StoryPersonaResponse,
)
from narrative_dag.chunk_spans import validate_and_build_chunks_from_spans
from narrative_dag.graph import run_analysis
from narrative_dag.llm import build_run_llm_bundle, resolve_run_llm_provider
from narrative_dag.nodes.ingestion import build_context_window
from narrative_dag.nodes.judgment import build_chunk_judgment_entry
from narrative_dag.quick_coach_diff import is_quick_coach_oob
from narrative_dag.quick_coach_story_chat import (
    QUICK_COACH_STORY_CHAT_USER_MESSAGE,
    format_quick_coach_advice_for_chat,
)
from narrative_dag.schemas import (
    Chunk,
    ChunkJudgmentEntry,
    EditorialReport,
    ElasticityResult,
    GenreIntention,
    QuickCoachAdvice,
    RawDocument,
)
from narrative_dag.store.bridge_population import ensure_characters, populate_chunk_character_bridges
from narrative_dag.explicit_context import build_explicit_context
from narrative_dag.pet_soul import load_pet_soul_markdown
from narrative_dag.persona.refresh_job import schedule_persona_refresh_after_analyze
from narrative_dag.store.document_store import DocumentStore
from narrative_dag.store.judgment_store import JudgmentStore
from narrative_dag.store.persona_store import PersonaStore
from narrative_dag.store.run_store import RunStore
from narrative_dag.store.inkblot_memory_store import InkblotMemoryStore
from narrative_dag.store.story_chat_store import StoryChatStore
from narrative_dag.inkblot_memory_jobs import schedule_inkblot_followup_jobs, schedule_inkblot_memory_close
from narrative_dag.story_chat import (
    build_inkblot_judgment_context,
    compact_older_turns_for_summary,
    run_inkblot_chat,
    story_wide_from_document_state,
    writer_memory_subset_for_prompt,
)


class NarrativeAnalysisService:
    """Orchestration entrypoint. All clients call this; CLI/API are thin adapters."""

    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path if db_path is not None else config_module.DEFAULT_DB_PATH
        self._conn = None
        self._run_store = None
        self._judgment_store = None
        self._document_store = None
        self._persona_store = None
        self._story_chat_store = None

    def _ensure_db(self):
        if self._conn is None:
            self._conn = init_db(self._db_path)
            self._run_store = RunStore(self._conn)
            self._judgment_store = JudgmentStore(self._conn)
            self._document_store = DocumentStore(self._conn)
            self._persona_store = PersonaStore(self._conn)
            self._story_chat_store = StoryChatStore(self._conn)

    def close(self) -> None:
        """Close SQLite connection; safe to call multiple times."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None
            self._run_store = None
            self._judgment_store = None
            self._document_store = None
            self._persona_store = None
            self._story_chat_store = None

    def __del__(self) -> None:  # pragma: no cover - defensive cleanup
        try:
            self.close()
        except Exception:
            pass

    def analyze_document(
        self,
        request: AnalyzeDocumentRequest,
        *,
        on_progress: Callable[[str, Any], None] | None = None,
    ) -> AnalyzeDocumentResponse:
        """Run full DAG: ingest -> represent -> detect -> conflict -> judge -> report."""
        try:
            self._ensure_db()
            assert self._run_store is not None and self._judgment_store is not None
            assert self._document_store is not None
            genre = GenreIntention(
                genre=request.genre,
                subgenre_tags=request.subgenre_tags,
                tone_descriptors=request.tone_descriptors,
                reference_authors=request.reference_authors,
                short_story_single_chapter=request.short_story_single_chapter,
            )
            doc = RawDocument(
                text=request.document_text,
                title=request.title,
                author=request.author,
            )
            client_chunks: list[Chunk] | None = None
            if request.chunks:
                try:
                    spans = [(c.chunk_id, c.start_char, c.end_char) for c in request.chunks]
                    client_chunks = validate_and_build_chunks_from_spans(request.document_text, spans)
                except ValueError as ve:
                    return AnalyzeDocumentResponse(
                        run_id="",
                        report=EditorialReport(run_id="", chunk_judgments=[], document_summary=""),
                        success=False,
                        error=str(ve),
                        document_id=request.document_id,
                        revision_id=None,
                    )

            only_ids: set[str] | None = None
            if request.only_chunk_ids:
                only_ids = set(request.only_chunk_ids)
                if not request.document_id:
                    return AnalyzeDocumentResponse(
                        run_id="",
                        report=EditorialReport(run_id="", chunk_judgments=[], document_summary=""),
                        success=False,
                        error="document_id is required for partial analysis",
                        document_id=None,
                        revision_id=None,
                    )
                br = self._run_store.get_run_row(request.base_run_id or "")
                if not br:
                    return AnalyzeDocumentResponse(
                        run_id="",
                        report=EditorialReport(run_id="", chunk_judgments=[], document_summary=""),
                        success=False,
                        error="base_run_id not found",
                        document_id=request.document_id,
                        revision_id=None,
                    )
                if br.get("document_id") != request.document_id:
                    return AnalyzeDocumentResponse(
                        run_id="",
                        report=EditorialReport(run_id="", chunk_judgments=[], document_summary=""),
                        success=False,
                        error="base_run_id belongs to a different document",
                        document_id=request.document_id,
                        revision_id=None,
                    )
                assert request.base_run_id is not None
                # New chunk ids (e.g. inserted middle sections) are allowed in only_chunk_ids; they are
                # analyzed fresh while non-target chunks merge from base_run_id.

            run_id = str(uuid.uuid4())

            document_id = request.document_id
            if not document_id:
                document_id = self._document_store.create_document(
                    title=request.title,
                    author=request.author,
                )

            revision_id = self._document_store.create_revision(
                document_id,
                request.document_text,
                parent_revision_id=request.revision_id,
            )
            self._document_store.record_revision_event(
                document_id,
                revision_id,
                "submit",
                from_revision_id=request.revision_id,
                metadata={"run_id": run_id},
            )

            if on_progress:
                on_progress(
                    "start",
                    {
                        "genre": request.genre,
                        "run_id": run_id,
                        "document_id": document_id,
                        "revision_id": revision_id,
                    },
                )

            analysis_kind = "partial" if only_ids else "full"
            self._run_store.save_run_meta(
                run_id,
                genre=request.genre,
                title=request.title,
                author=request.author,
                document_id=document_id,
                revision_id=revision_id,
                analysis_kind=analysis_kind,
            )

            def on_chunk_done(run_id_arg, chunk_id, position, artifact_dict, judgment, elasticity):
                self._run_store.save_chunk_artifact(run_id_arg, chunk_id, position, artifact_dict)
                self._judgment_store.save_judgment(
                    run_id_arg, chunk_id, judgment, source="editor_judge", rationale=""
                )

            seed_ds = (
                self._run_store.get_document_state(request.base_run_id)
                if only_ids and request.base_run_id
                else None
            )
            llm_bundle = build_run_llm_bundle(resolve_run_llm_provider(request.provider))
            state, chunk_judgments = run_analysis(
                raw_document=doc,
                genre_intention=genre,
                run_id=run_id,
                db_path=self._db_path,
                on_chunk_done=on_chunk_done,
                client_chunks=client_chunks,
                only_chunk_ids=only_ids,
                seed_document_state=seed_ds,
                bundle=llm_bundle,
            )

            final_chunk_judgments = list(chunk_judgments)
            if only_ids and request.base_run_id:
                base_id = request.base_run_id
                chunks = state.get("chunks") or []
                gs = state.get("global_summary", "")
                base_ds = self._run_store.get_document_state(base_id)
                for i, ch in enumerate(chunks):
                    if ch.id not in only_ids:
                        base_art = self._run_store.get_chunk_artifact(base_id, ch.id)
                        if not base_art:
                            return AnalyzeDocumentResponse(
                                run_id="",
                                report=EditorialReport(run_id="", chunk_judgments=[], document_summary=""),
                                success=False,
                                error=f"missing base artifact for chunk {ch.id}",
                                document_id=document_id,
                                revision_id=revision_id,
                            )
                        art = json.loads(json.dumps(base_art))
                        cw = build_context_window(chunks, ch.id, global_summary=gs)
                        art["target_chunk"] = ch.model_dump()
                        art["context_window"] = {
                            "target_chunk": cw.target_chunk.model_dump(),
                            "previous_chunks": [c.model_dump() for c in cw.previous_chunks],
                            "next_chunks": [c.model_dump() for c in cw.next_chunks],
                            "global_summary": cw.global_summary,
                        }
                        self._run_store.save_chunk_artifact(run_id, ch.id, i, art)
                        jv = self._judgment_store.get_latest_judgment(base_id, ch.id)
                        if jv:
                            self._judgment_store.save_judgment(
                                run_id,
                                ch.id,
                                jv.judgment,
                                source="editor_judge",
                                rationale="copied from base run",
                            )
                merged: list[ChunkJudgmentEntry] = []
                for i, ch in enumerate(chunks):
                    if ch.id in only_ids:
                        entry = next((x for x in chunk_judgments if x.chunk_id == ch.id), None)
                        if entry:
                            merged.append(entry)
                    else:
                        jv = self._judgment_store.get_latest_judgment(run_id, ch.id)
                        if jv:
                            base_art = self._run_store.get_chunk_artifact(base_id, ch.id)
                            merged.append(
                                build_chunk_judgment_entry(
                                    ch.id,
                                    i,
                                    jv.judgment,
                                    ElasticityResult(),
                                    critic_result=base_art.get("critic_result") if base_art else None,
                                    defense_result=base_art.get("defense_result") if base_art else None,
                                    evidence_synthesis_result=base_art.get("evidence_synthesis_result") if base_art else None,
                                )
                            )
                final_chunk_judgments = merged
                merged_ds = state.get("document_state")
                if merged_ds is not None:
                    self._run_store.save_document_state(run_id, merged_ds)
                elif base_ds is not None:
                    self._run_store.save_document_state(run_id, base_ds)
            elif state.get("document_state") is not None:
                self._run_store.save_document_state(run_id, state["document_state"])

            chunks = state.get("chunks") or []
            if revision_id and chunks:
                self._document_store.replace_chunk_versions(revision_id, chunks)
                cv_map = self._document_store.get_chunk_version_map(revision_id)
                char_db = state.get("character_database")
                name_to_id = ensure_characters(self._conn, document_id, char_db)
                for ch in chunks:
                    cv_id = cv_map.get(ch.id)
                    if cv_id:
                        populate_chunk_character_bridges(
                            self._conn,
                            cv_id,
                            ch,
                            char_db,
                            name_to_id,
                        )
                        for cj in final_chunk_judgments:
                            if cj.chunk_id == ch.id:
                                self._document_store.save_analytic_fact(
                                    run_id,
                                    revision_id,
                                    "editor_judgment",
                                    cj.judgment.model_dump(),
                                    chunk_version_id=cv_id,
                                )
                                break

            er = state.get("editorial_report")
            doc_sum = "Analysis complete."
            if isinstance(er, dict):
                doc_sum = er.get("document_summary") or doc_sum
            elif er is not None and getattr(er, "document_summary", None):
                doc_sum = str(er.document_summary)

            report = EditorialReport(
                run_id=run_id,
                chunk_judgments=final_chunk_judgments,
                document_summary=doc_sum,
            )

            if on_progress:
                on_progress("complete", {"run_id": run_id, "revision_id": revision_id, "document_id": document_id})
            if analysis_kind == "full" and revision_id and document_id:
                schedule_persona_refresh_after_analyze(
                    self._db_path,
                    document_id=document_id,
                    revision_id=revision_id,
                    run_id=run_id,
                    provider=request.provider,
                )
            return AnalyzeDocumentResponse(
                run_id=run_id,
                report=report,
                success=True,
                document_id=document_id,
                revision_id=revision_id,
                analysis_kind=analysis_kind,
            )
        except Exception as e:
            return AnalyzeDocumentResponse(
                run_id="",
                report=EditorialReport(run_id="", chunk_judgments=[], document_summary=""),
                success=False,
                error=str(e),
            )

    def quick_coach_advice(
        self,
        run_id: str,
        chunk_id: str,
        revision_id: str,
        focus: str | None,
        *,
        current_chunk_text: str | None = None,
        short_story_single_chapter: bool = False,
        provider: str | None = None,
    ) -> QuickCoachResponse:
        """Single LLM call for sparkle quick coach; expects validated run_id + chunk_id."""
        try:
            self._ensure_db()
            assert self._run_store is not None and self._document_store is not None
            bundle = self._run_store.get_context_bundle(run_id, chunk_id)
            if not bundle:
                return QuickCoachResponse(
                    success=False,
                    error="chunk not found in run",
                    error_code="chunk_not_in_run",
                    revision_id=revision_id,
                )
            from narrative_dag.nodes.quick_coach import run_quick_coach

            qc_llm = build_run_llm_bundle(resolve_run_llm_provider(provider)).llm_quick_coach
            analyzed_text = bundle.target_chunk.text
            current = current_chunk_text
            if current is None:
                current = self._document_store.get_revision_chunk_text(revision_id, chunk_id)

            if current is not None:
                oob, delta, thr = is_quick_coach_oob(analyzed_text, current)
                if oob:
                    return QuickCoachResponse(
                        success=False,
                        error=(
                            "This section changed too much since the last analysis. "
                            "Run a full manuscript analysis (Submit All) or reanalyze this section."
                        ),
                        error_code="quick_coach_oob",
                        requires_reanalysis=True,
                        delta_chars=delta,
                        threshold_chars=thr,
                        analyzed_char_len=len(analyzed_text),
                        current_char_len=len(current),
                        revision_id=revision_id,
                        run_id=run_id,
                    )
                advice = run_quick_coach(
                    bundle,
                    focus,
                    llm=qc_llm,
                    current_revision_text=current,
                    short_story_single_chapter=short_story_single_chapter,
                )
            else:
                advice = run_quick_coach(
                    bundle,
                    focus,
                    llm=qc_llm,
                    short_story_single_chapter=short_story_single_chapter,
                )

            return QuickCoachResponse(
                success=True,
                advice=advice,
                run_id=run_id,
                revision_id=revision_id,
            )
        except Exception as e:
            return QuickCoachResponse(success=False, error=str(e), revision_id=revision_id)

    def append_quick_coach_story_chat_turns(
        self,
        document_id: str,
        revision_id: str,
        story_chat_session_id: str | None,
        chunk_id: str,
        advice: QuickCoachAdvice,
    ) -> tuple[str | None, bool]:
        """Append synthetic user + assistant turns; create session if needed. Invalid session_id is ignored."""
        try:
            self._ensure_db()
            assert (
                self._document_store is not None
                and self._persona_store is not None
                and self._story_chat_store is not None
            )
            persona = self._persona_store.get_latest_snapshot(document_id)
            used_ver = persona["version"] if persona else None

            session_id: str | None = story_chat_session_id
            if session_id:
                sess = self._story_chat_store.get_session(session_id)
                if not sess or sess.get("document_id") != document_id:
                    session_id = None

            if not session_id:
                session_id = self._story_chat_store.create_session(
                    document_id,
                    revision_id=revision_id,
                    persona_version=used_ver,
                )

            user_manifest: dict[str, Any] = {"source": "quick_coach", "chunk_id": chunk_id}
            self._story_chat_store.append_turn(
                session_id,
                role="user",
                content=QUICK_COACH_STORY_CHAT_USER_MESSAGE,
                context_manifest=user_manifest,
            )
            assistant_body = format_quick_coach_advice_for_chat(advice)
            self._story_chat_store.append_turn(
                session_id,
                role="assistant",
                content=assistant_body,
                context_manifest={"follows": user_manifest, "source": "quick_coach"},
            )

            if persona:
                self._persona_store.append_event(
                    document_id,
                    "story_chat_turn",
                    "user",
                    source_id=session_id,
                    revision_id=revision_id,
                    payload={"message": QUICK_COACH_STORY_CHAT_USER_MESSAGE[:2000], "source": "quick_coach"},
                )

            return (session_id, True)
        except Exception:
            return (None, False)

    def chat(
        self,
        request: ChatRequest,
        *,
        on_progress: Callable[[str, Any], None] | None = None,
    ) -> ChatResponse:
        """Chat with judge about a chunk: explain or reconsider (context-pinned)."""
        try:
            self._ensure_db()
            assert self._run_store is not None and self._judgment_store is not None
            if on_progress:
                on_progress("chat_start", {"chunk_id": request.chunk_id, "mode": request.mode})
            bundle = self._run_store.get_context_bundle(request.run_id, request.chunk_id)
            if not bundle:
                return ChatResponse(reply="Run or chunk not found.", success=False)
            latest = self._judgment_store.get_latest_judgment(request.run_id, request.chunk_id)
            if latest:
                from narrative_dag.schemas import ContextBundle

                bundle = ContextBundle(
                    target_chunk=bundle.target_chunk,
                    context_window=bundle.context_window,
                    document_state=bundle.document_state,
                    detector_results=bundle.detector_results,
                    critic_result=bundle.critic_result,
                    defense_result=bundle.defense_result,
                    current_judgment=latest.judgment,
                    genre_intention=bundle.genre_intention,
                )
            from narrative_dag.nodes.interaction import run_judge_explain, run_judge_reconsider

            chat_llm = build_run_llm_bundle(resolve_run_llm_provider(request.provider)).llm_chat
            chat_state = {
                "context_bundle": bundle,
                "user_message": request.user_message,
                "_llm": chat_llm,
            }
            if request.mode == "explain":
                out = run_judge_explain(chat_state)
            else:
                out = run_judge_reconsider(chat_state)
            reply = out.get("chat_reply", "")
            updated = out.get("updated_judgment")
            jv = None
            if updated:
                jv = self._judgment_store.save_judgment(
                    request.run_id,
                    request.chunk_id,
                    updated,
                    source="judge_reconsideration",
                    rationale=request.user_message,
                )
            if on_progress:
                on_progress("chat_complete", {})
            return ChatResponse(reply=reply, updated_judgment=updated, judgment_version=jv, success=True)
        except Exception as e:
            return ChatResponse(reply="", success=False, error=str(e))

    def get_story_persona(self, document_id: str) -> StoryPersonaResponse:
        """Latest inkblot persona snapshot and soul metadata for a document."""
        try:
            self._ensure_db()
            assert self._persona_store is not None and self._run_store is not None
            soul = load_pet_soul_markdown(document_id)
            snap = self._persona_store.get_latest_snapshot(document_id)
            run_id = self._run_store.find_latest_run_for_document_with_story_map(document_id)
            pending = JobStore(self._conn).has_pending_persona_refresh(document_id)
            mem_row = InkblotMemoryStore(self._conn).get_row(document_id)
            out_snap: dict[str, Any] | None = None
            if snap:
                out_snap = {
                    "version": snap["version"],
                    "state": snap["state"],
                    "deterministic": snap["deterministic_json"],
                    "llm_snapshot": snap["llm_snapshot_json"],
                    "pet_style_policy": snap["pet_style_policy_json"],
                    "source_run_id": snap["source_run_id"],
                    "created_at": snap["created_at"],
                }
            return StoryPersonaResponse(
                document_id=document_id,
                snapshot=out_snap,
                soul_loaded=bool(soul["markdown"]),
                soul_paths=list(soul["paths"]),
                persona_refresh_pending=pending,
                latest_run_id=run_id,
                inkblot_memory=mem_row["payload"] if mem_row else None,
                inkblot_memory_updated_at=mem_row["updated_at"] if mem_row else None,
            )
        except Exception:
            return StoryPersonaResponse(
                document_id=document_id,
                snapshot=None,
                soul_loaded=False,
                soul_paths=[],
                persona_refresh_pending=False,
                latest_run_id=None,
                inkblot_memory=None,
                inkblot_memory_updated_at=None,
            )

    def story_chat_session_close(
        self,
        document_id: str,
        session_id: str,
        request: StoryChatSessionCloseRequest | None = None,
    ) -> StoryChatSessionCloseResponse:
        """Enqueue full-session close summary for Inkblot memory (panel closed)."""
        try:
            self._ensure_db()
            assert self._story_chat_store is not None
            req = request or StoryChatSessionCloseRequest()
            sess = self._story_chat_store.get_session(session_id)
            if not sess or sess.get("document_id") != document_id:
                return StoryChatSessionCloseResponse(success=False, scheduled=False, error="Invalid session")
            turns = self._story_chat_store.list_turns(session_id)
            last_idx = None
            if turns:
                last_idx = max(int(t.get("turn_index", 0)) for t in turns)
            lt = req.last_turn_index if req.last_turn_index is not None else last_idx
            scheduled = schedule_inkblot_memory_close(
                self._db_path,
                document_id=document_id,
                session_id=session_id,
                last_turn_index=lt,
                provider=req.provider,
            )
            return StoryChatSessionCloseResponse(success=True, scheduled=scheduled)
        except Exception as e:
            return StoryChatSessionCloseResponse(success=False, scheduled=False, error=str(e))

    def story_chat(self, document_id: str, request: StoryChatRequest) -> StoryChatResponse:
        """Inkblot chat with explicit manuscript context (no RAG)."""
        try:
            self._ensure_db()
            assert (
                self._document_store is not None
                and self._persona_store is not None
                and self._story_chat_store is not None
                and self._run_store is not None
            )
            rev_id = request.revision_id
            if not rev_id:
                cur = self._document_store.get_current_revision_for_document(document_id)
                if not cur:
                    return StoryChatResponse(
                        success=False,
                        error="No revision for document.",
                        error_code="no_revision",
                        recovery_hints=["Create a revision by saving the manuscript."],
                    )
                rev_id = str(cur["revision_id"])

            manifest, excerpt, err = build_explicit_context(
                self._document_store,
                revision_id=rev_id,
                chunk_ids=request.chunk_ids,
                chapter_id=request.chapter_id,
                max_words=request.max_words,
            )
            if err:
                hints = {
                    "chunk_not_found": [
                        "Select chunk ids that exist on this revision.",
                        "Run Submit All / analyze so chunk spans are recorded.",
                    ],
                    "revision_not_found": ["Use a valid revision_id for this document."],
                    "no_manuscript": ["Save the manuscript before chatting."],
                    "chapter_not_found": [
                        "Pick a chapter_id from GET /v1/documents/{id}/chapters.",
                        "Or pass chunk_ids to scope the chat.",
                    ],
                }
                return StoryChatResponse(
                    success=False,
                    error=f"Cannot build context: {err}",
                    error_code=err,
                    context_manifest=manifest,
                    recovery_hints=hints.get(err, []),
                )

            judgment_context = None
            if manifest.get("scope") == "chunks" and manifest.get("chunk_ids"):
                chunk_ids_list = list(manifest["chunk_ids"])
                j_run = self._run_store.find_latest_run_for_revision(rev_id)
                found_map: dict[str, bool]
                if j_run:
                    judgment_context, found_map = build_inkblot_judgment_context(
                        self._run_store, j_run, chunk_ids_list
                    )
                else:
                    found_map = {cid: False for cid in chunk_ids_list}
                manifest = {
                    **manifest,
                    "judgment_run_id": j_run,
                    "chunk_judgment_artifact_present": found_map,
                }

            soul = load_pet_soul_markdown(document_id)
            mem_store = InkblotMemoryStore(self._conn)
            wm_for_prompt = writer_memory_subset_for_prompt(mem_store.get_payload(document_id))
            persona = self._persona_store.get_latest_snapshot(document_id)
            run_id = self._run_store.find_latest_run_for_document_with_story_map(document_id)
            if not run_id:
                run_id = self._run_store.find_latest_run_for_document(document_id)
            ds = self._run_store.get_document_state(run_id) if run_id else None
            story_wide = story_wide_from_document_state(ds)
            deterministic: dict[str, Any] = (
                persona["deterministic_json"] if persona else {"state": "bootstrap", "note": "no persona snapshot yet"}
            )
            pet_style = persona.get("pet_style_policy_json") if persona else None
            llm_snap = persona.get("llm_snapshot_json") if persona else None
            used_ver = persona["version"] if persona else None

            session_id = request.session_id
            if session_id:
                sess = self._story_chat_store.get_session(session_id)
                if not sess or sess.get("document_id") != document_id:
                    return StoryChatResponse(
                        success=False,
                        error="Invalid session_id for this document.",
                        error_code="invalid_session",
                    )
            else:
                session_id = self._story_chat_store.create_session(
                    document_id,
                    revision_id=rev_id,
                    persona_version=used_ver,
                )

            history_before = self._story_chat_store.list_turns(session_id)
            self._story_chat_store.append_turn(
                session_id,
                role="user",
                content=request.user_message,
                context_manifest=manifest,
            )

            prior_for_model = history_before[-config_module.STORY_CHAT_ACTIVE_TURNS :]
            older = compact_older_turns_for_summary(
                history_before, config_module.STORY_CHAT_ACTIVE_TURNS
            )
            user_msg = request.user_message
            if older:
                user_msg = f"[Earlier turns summary]\n{older}\n\n{request.user_message}"

            answer = run_inkblot_chat(
                user_message=user_msg,
                manuscript_excerpt=excerpt,
                soul_markdown=soul["markdown"],
                deterministic=deterministic if isinstance(deterministic, dict) else {},
                pet_style_policy=pet_style if isinstance(pet_style, dict) else None,
                llm_snapshot=llm_snap if isinstance(llm_snap, dict) else None,
                story_wide=story_wide,
                context_manifest=manifest,
                prior_turns=prior_for_model,
                provider=request.provider,
                writer_memory=wm_for_prompt,
                judgment_context=judgment_context,
            )

            self._story_chat_store.append_turn(
                session_id,
                role="assistant",
                content=answer,
                context_manifest={"follows": manifest},
            )

            if persona:
                self._persona_store.append_event(
                    document_id,
                    "story_chat_turn",
                    "user",
                    source_id=session_id,
                    revision_id=rev_id,
                    payload={"message": request.user_message[:2000]},
                )

            trunc_note = None
            if manifest.get("truncated"):
                trunc_note = f"Excerpt truncated to {request.max_words} words."

            pending = JobStore(self._conn).has_pending_persona_refresh(document_id)
            schedule_inkblot_followup_jobs(
                self._db_path,
                document_id=document_id,
                session_id=session_id,
                provider=request.provider,
            )
            mem_after = mem_store.get_row(document_id)
            return StoryChatResponse(
                answer=answer,
                used_persona_version=used_ver,
                session_id=session_id,
                context_manifest=manifest,
                truncation_notice=trunc_note,
                confidence=1.0 if excerpt else None,
                persona_refresh_pending=pending,
                success=True,
                inkblot_memory_updated_at=mem_after["updated_at"] if mem_after else None,
            )
        except Exception as e:
            return StoryChatResponse(success=False, error=str(e), error_code="story_chat_error")
