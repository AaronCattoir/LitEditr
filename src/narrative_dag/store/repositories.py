"""Storage interfaces and SQLite implementations for RunStore and JudgmentStore."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from narrative_dag.schemas import (
    ContextBundle,
    DocumentState,
    EditorJudgment,
    JudgmentVersion,
)


class RunStoreInterface(ABC):
    """Interface for persisting run artifacts (chunks, context, document state)."""

    @abstractmethod
    def save_run_meta(self, run_id: str, genre: str | None, title: str | None, author: str | None) -> None:
        """Create or update run metadata."""
        ...

    @abstractmethod
    def save_chunk_artifact(self, run_id: str, chunk_id: str, position: int, payload: dict[str, Any]) -> None:
        """Persist one chunk's full artifact (context, analysis, detectors, critic, defense, judgment)."""
        ...

    @abstractmethod
    def save_document_state(self, run_id: str, state: DocumentState) -> None:
        """Persist document-level state for the run."""
        ...

    @abstractmethod
    def get_chunk_artifact(self, run_id: str, chunk_id: str) -> dict[str, Any] | None:
        """Load one chunk's artifact by run_id + chunk_id."""
        ...

    @abstractmethod
    def get_document_state(self, run_id: str) -> DocumentState | None:
        """Load document state for the run."""
        ...

    @abstractmethod
    def get_context_bundle(self, run_id: str, chunk_id: str) -> ContextBundle | None:
        """Assemble ContextBundle for interaction layer from persisted artifacts."""
        ...


class JudgmentStoreInterface(ABC):
    """Interface for persisting judgment versions (immutable audit trail)."""

    @abstractmethod
    def save_judgment(
        self,
        run_id: str,
        chunk_id: str,
        judgment: EditorJudgment,
        source: str,
        rationale: str,
    ) -> JudgmentVersion:
        """Append a new judgment version; returns the new version."""
        ...

    @abstractmethod
    def get_latest_judgment(self, run_id: str, chunk_id: str) -> JudgmentVersion | None:
        """Get the current active (latest) judgment for the chunk."""
        ...

    @abstractmethod
    def get_judgment_history(self, run_id: str, chunk_id: str) -> list[JudgmentVersion]:
        """Get full audit trail for the chunk, oldest first."""
        ...
