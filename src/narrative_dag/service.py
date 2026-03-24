"""Transport-agnostic application service: single entrypoint for CLI, API, and future GUI."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

from narrative_dag.config import DEFAULT_DB_PATH
from narrative_dag.contracts import (
    AnalyzeDocumentRequest,
    AnalyzeDocumentResponse,
    ChatRequest,
    ChatResponse,
)
from narrative_dag.graph import run_analysis
import narrative_dag.llm as llm_runtime
import narrative_dag.mem0_hooks as mem0_hooks
from narrative_dag.db import init_db
from narrative_dag.schemas import (
    EditorialReport,
    GenreIntention,
    RawDocument,
)
from narrative_dag.store.bridge_population import ensure_characters, populate_chunk_character_bridges
from narrative_dag.store.document_store import DocumentStore
from narrative_dag.store.judgment_store import JudgmentStore
from narrative_dag.store.run_store import RunStore


class NarrativeAnalysisService:
    """Orchestration entrypoint. All clients call this; CLI/API are thin adapters."""

    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path if db_path is not None else DEFAULT_DB_PATH
        self._conn = None
        self._run_store = None
        self._judgment_store = None
        self._document_store = None

    def _ensure_db(self):
        if self._conn is None:
            self._conn = init_db(self._db_path)
            self._run_store = RunStore(self._conn)
            self._judgment_store = JudgmentStore(self._conn)
            self._document_store = DocumentStore(self._conn)

    def close(self) -> None:
        """Close SQLite connection; safe to call multiple times."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None
            self._run_store = None
            self._judgment_store = None
            self._document_store = None

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
            )
            doc = RawDocument(
                text=request.document_text,
                title=request.title,
                author=request.author,
            )
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

            self._run_store.save_run_meta(
                run_id,
                genre=request.genre,
                title=request.title,
                author=request.author,
                document_id=document_id,
                revision_id=revision_id,
                analysis_kind="full",
            )

            def on_chunk_done(run_id_arg, chunk_id, position, artifact_dict, judgment, elasticity):
                self._run_store.save_chunk_artifact(run_id_arg, chunk_id, position, artifact_dict)
                self._judgment_store.save_judgment(
                    run_id_arg, chunk_id, judgment, source="editor_judge", rationale=""
                )

            state, chunk_judgments = run_analysis(
                raw_document=doc,
                genre_intention=genre,
                run_id=run_id,
                db_path=self._db_path,
                on_chunk_done=on_chunk_done,
            )

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
                        # Persist judgment fact for analytics / star schema
                        for cj in chunk_judgments:
                            if cj.chunk_id == ch.id:
                                self._document_store.save_analytic_fact(
                                    run_id,
                                    revision_id,
                                    "editor_judgment",
                                    cj.judgment.model_dump(),
                                    chunk_version_id=cv_id,
                                )
                                break

            doc_state = state.get("document_state")
            if doc_state is not None:
                self._run_store.save_document_state(run_id, doc_state)

            report = state.get("editorial_report")
            if isinstance(report, dict):
                report = EditorialReport(
                    run_id=report.get("run_id", run_id),
                    chunk_judgments=report.get("chunk_judgments", chunk_judgments),
                    document_summary=report.get("document_summary", ""),
                )
            elif report is None:
                report = EditorialReport(
                    run_id=run_id,
                    chunk_judgments=chunk_judgments,
                    document_summary="Analysis complete.",
                )

            mem0_hooks.sync_document_summary_if_enabled(
                user_id=document_id,
                document_id=document_id,
                revision_id=revision_id,
                document_summary=report.document_summary,
                genre=request.genre,
            )

            if on_progress:
                on_progress("complete", {"run_id": run_id, "revision_id": revision_id, "document_id": document_id})
            return AnalyzeDocumentResponse(
                run_id=run_id,
                report=report,
                success=True,
                document_id=document_id,
                revision_id=revision_id,
            )
        except Exception as e:
            return AnalyzeDocumentResponse(
                run_id="",
                report=EditorialReport(run_id="", chunk_judgments=[], document_summary=""),
                success=False,
                error=str(e),
            )

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

            chat_state = {
                "context_bundle": bundle,
                "user_message": request.user_message,
                "_llm": llm_runtime.get_llm(),
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
