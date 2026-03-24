"""LLM runtime factory and structured invocation helpers."""

from __future__ import annotations

import logging
import os
import warnings
from typing import Any, TypeVar

from pydantic import BaseModel

from narrative_dag.config import (
    DEFAULT_GEMINI_FAST_MODEL,
    DEFAULT_GEMINI_MODEL,
    DEFAULT_GEMINI_PRO_MODEL,
    DEFAULT_LLM_PROVIDER,
    DEFAULT_LLM_TEMPERATURE,
    DEFAULT_OPENAI_FAST_MODEL,
    DEFAULT_OPENAI_MODEL,
    DEFAULT_OPENAI_PRO_MODEL,
    DEFAULT_VERTEX_FAST_MODEL,
    DEFAULT_VERTEX_MODEL,
    DEFAULT_VERTEX_PRO_MODEL,
)

TModel = TypeVar("TModel", bound=BaseModel)

# Python 3.14 currently triggers noisy third-party warnings from legacy
# pydantic-v1 compatibility layers; hide these so real runtime errors stand out.
warnings.filterwarnings(
    "ignore",
    message=r"Core Pydantic V1 functionality isn't compatible with Python 3\.14 or greater\.",
    category=UserWarning,
)


class _IgnoreUnsupportedSchemaKeyFilter(logging.Filter):
    """Drop noisy schema-key warnings from provider adapters."""

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        if "not supported in schema, ignoring" in msg and "additionalProperties" in msg:
            return False
        return True


def _install_logging_filters() -> None:
    noise_filter = _IgnoreUnsupportedSchemaKeyFilter()
    for logger_name in (
        "google",
        "google.genai",
        "langchain_google_genai",
        "langchain_google_genai._function_utils",
        "langchain_google_vertexai",
        "langchain_google_vertexai.functions_utils",
    ):
        logger = logging.getLogger(logger_name)
        if not any(isinstance(f, _IgnoreUnsupportedSchemaKeyFilter) for f in logger.filters):
            logger.addFilter(noise_filter)
    root_logger = logging.getLogger()
    if not any(isinstance(f, _IgnoreUnsupportedSchemaKeyFilter) for f in root_logger.filters):
        root_logger.addFilter(noise_filter)
    # The noisy "Key 'additionalProperties' ..." line is emitted by this module.
    logging.getLogger("langchain_google_genai._function_utils").setLevel(logging.ERROR)
    logging.getLogger("langchain_google_vertexai.functions_utils").setLevel(logging.ERROR)


_install_logging_filters()


def _require_env_any(names: list[str]) -> str:
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value
    raise RuntimeError(f"Missing required API key env var. Expected one of: {', '.join(names)}")


def _resolve_stage_model(provider: str, stage: str | None) -> str | None:
    """Return stage-specific default model for provider.

    Stages:
    - detector: high-volume detector calls
    - judgment/conflict: high-importance decision calls
    - anything else: provider default model
    """
    stage_key = (stage or "").strip().lower()
    if provider == "gemini":
        if stage_key == "detector":
            return DEFAULT_GEMINI_FAST_MODEL
        if stage_key in {"judgment", "conflict"}:
            return DEFAULT_GEMINI_PRO_MODEL
        return DEFAULT_GEMINI_MODEL
    if provider == "vertex":
        if stage_key == "detector":
            return DEFAULT_VERTEX_FAST_MODEL
        if stage_key in {"judgment", "conflict"}:
            return DEFAULT_VERTEX_PRO_MODEL
        return DEFAULT_VERTEX_MODEL
    if provider == "openai":
        if stage_key == "detector":
            return DEFAULT_OPENAI_FAST_MODEL
        if stage_key in {"judgment", "conflict"}:
            return DEFAULT_OPENAI_PRO_MODEL
        return DEFAULT_OPENAI_MODEL
    return None


def get_llm(
    provider: str | None = None,
    model: str | None = None,
    temperature: float | None = None,
    stage: str | None = None,
) -> Any:
    """Return a chat model instance for the configured provider."""
    selected_provider = (provider or DEFAULT_LLM_PROVIDER).strip().lower()
    selected_temperature = DEFAULT_LLM_TEMPERATURE if temperature is None else temperature

    resolved_model = model or _resolve_stage_model(selected_provider, stage)

    if selected_provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        logging.getLogger("langchain_google_genai._function_utils").disabled = True

        api_key = _require_env_any(["GEMINI_API_KEY", "GOOGLE_API_KEY"])
        return ChatGoogleGenerativeAI(
            model=resolved_model or DEFAULT_GEMINI_MODEL,
            temperature=selected_temperature,
            max_retries=6,
            google_api_key=api_key,
        )

    if selected_provider == "openai":
        from langchain_openai import ChatOpenAI

        _require_env_any(["OPENAI_API_KEY"])
        return ChatOpenAI(
            model=resolved_model or DEFAULT_OPENAI_MODEL,
            temperature=selected_temperature,
            max_retries=2,
        )

    if selected_provider == "vertex":
        from langchain_core._api.deprecation import LangChainDeprecationWarning

        warnings.filterwarnings(
            "ignore",
            message=r".*ChatVertexAI.*deprecated.*",
            category=LangChainDeprecationWarning,
        )
        from langchain_google_vertexai import ChatVertexAI

        project = os.getenv("GOOGLE_CLOUD_PROJECT", "").strip()
        location = os.getenv("GOOGLE_CLOUD_LOCATION", "global").strip()
        if not project:
            raise RuntimeError("Missing GOOGLE_CLOUD_PROJECT for Vertex AI provider.")
        return ChatVertexAI(
            model_name=resolved_model or DEFAULT_VERTEX_MODEL,
            project=project,
            location=location,
            temperature=selected_temperature,
            max_retries=6,
        )

    raise RuntimeError(
        f"Unsupported LLM provider '{selected_provider}'. Supported: gemini, vertex, openai."
    )


def structured_invoke(llm: Any, messages: list[Any], schema: type[TModel]) -> TModel:
    """Invoke LLM with structured output mapped to a Pydantic schema."""
    return llm.with_structured_output(schema).invoke(messages)

