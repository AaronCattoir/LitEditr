"""LLM runtime factory and structured invocation helpers."""

from __future__ import annotations

import logging
import os
import sys
import time
import warnings
from dataclasses import dataclass
from typing import Any, Literal, TypeVar

from pydantic import BaseModel

from narrative_dag.config import (
    DEFAULT_GEMINI_FAST_MODEL,
    DEFAULT_GEMINI_MODEL,
    DEFAULT_GEMINI_PRO_MODEL,
    DEFAULT_LLM_PROVIDER,
    DEFAULT_LLM_PROVIDER_CHAT,
    DEFAULT_LLM_PROVIDER_CONFLICT,
    DEFAULT_LLM_PROVIDER_DEFAULT_STAGE,
    DEFAULT_LLM_PROVIDER_DETECTOR,
    DEFAULT_LLM_PROVIDER_JUDGMENT,
    DEFAULT_LLM_PROVIDER_QUICK_COACH,
    DEFAULT_LLM_TEMPERATURE,
    DEFAULT_LLM_TIMEOUT_S,
    DEFAULT_OPENAI_FAST_MODEL,
    DEFAULT_OPENAI_MODEL,
    DEFAULT_OPENAI_PRO_MODEL,
    DEFAULT_VERTEX_FAST_MODEL,
    DEFAULT_VERTEX_MODEL,
    DEFAULT_VERTEX_PRO_MODEL,
)

TModel = TypeVar("TModel", bound=BaseModel)

BetaLLMProvider = Literal["openai", "gemini"]
BETA_LLM_PROVIDERS: frozenset[str] = frozenset({"openai", "gemini"})


@dataclass
class RunLLMBundle:
    """Per-run chat clients: one provider, stage-appropriate models (detector/judgment tiers)."""

    provider: str
    llm: Any
    llm_detector: Any
    llm_judge: Any
    llm_quick_coach: Any
    llm_chat: Any


def is_openai_configured() -> bool:
    return bool(os.getenv("OPENAI_API_KEY", "").strip())


def is_gemini_configured() -> bool:
    return bool(os.getenv("GEMINI_API_KEY", "").strip() or os.getenv("GOOGLE_API_KEY", "").strip())


def is_beta_llm_provider_configured(provider: str) -> bool:
    p = provider.strip().lower()
    if p == "openai":
        return is_openai_configured()
    if p == "gemini":
        return is_gemini_configured()
    return False


def default_beta_llm_provider() -> str:
    """Effective default for the beta (openai/gemini) path from env."""
    return resolve_run_llm_provider(None)


def resolve_run_llm_provider(requested: str | None) -> str:
    """Map API/config to a beta provider. Vertex (or unknown env default) coerces to gemini for bundles."""
    if requested:
        r = requested.strip().lower()
        if r in BETA_LLM_PROVIDERS:
            return r
    d = DEFAULT_LLM_PROVIDER.strip().lower()
    if d in BETA_LLM_PROVIDERS:
        return d
    if d == "vertex":
        return "gemini"
    return "gemini"


def build_run_llm_bundle(provider: str) -> RunLLMBundle:
    """Construct per-run clients for the beta path (openai or gemini only)."""
    p = provider.strip().lower()
    if p not in BETA_LLM_PROVIDERS:
        raise ValueError(f"Unsupported beta LLM provider '{provider}'. Use one of: {sorted(BETA_LLM_PROVIDERS)}.")
    return RunLLMBundle(
        provider=p,
        llm=get_llm(provider=p, stage=None),
        llm_detector=get_llm(provider=p, stage="detector"),
        llm_judge=get_llm(provider=p, stage="judgment"),
        llm_quick_coach=get_llm(provider=p, stage="quick_coach"),
        llm_chat=get_llm(provider=p, stage="chat"),
    )


def runtime_providers_public_view() -> dict[str, Any]:
    """Safe for GET /v1/runtime/providers: no secrets, only ids, flags, and resolved default model names."""
    return {
        "default_provider": default_beta_llm_provider(),
        "providers": [
            {
                "id": "gemini",
                "configured": is_gemini_configured(),
                "models": {
                    "default": DEFAULT_GEMINI_MODEL,
                    "fast": DEFAULT_GEMINI_FAST_MODEL,
                    "pro": DEFAULT_GEMINI_PRO_MODEL,
                },
            },
            {
                "id": "openai",
                "configured": is_openai_configured(),
                "models": {
                    "default": DEFAULT_OPENAI_MODEL,
                    "fast": DEFAULT_OPENAI_FAST_MODEL,
                    "pro": DEFAULT_OPENAI_PRO_MODEL,
                },
            },
        ],
    }

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


def _resolve_stage_provider(stage: str | None) -> str:
    stage_key = (stage or "").strip().lower()
    if stage_key == "detector":
        return DEFAULT_LLM_PROVIDER_DETECTOR
    if stage_key == "judgment":
        return DEFAULT_LLM_PROVIDER_JUDGMENT
    if stage_key == "conflict":
        return DEFAULT_LLM_PROVIDER_CONFLICT
    if stage_key == "quick_coach":
        return DEFAULT_LLM_PROVIDER_QUICK_COACH
    if stage_key == "chat":
        return DEFAULT_LLM_PROVIDER_CHAT
    return DEFAULT_LLM_PROVIDER_DEFAULT_STAGE or DEFAULT_LLM_PROVIDER


# Max characters for assistant text extracted for UI (prevents pathological payloads).
_DEFAULT_MAX_ASSISTANT_TEXT_CHARS = 2_000_000


def _clip_text(s: str, max_chars: int) -> str:
    if max_chars <= 0:
        return ""
    if len(s) <= max_chars:
        return s
    return s[:max_chars]


def _text_from_content_block_dict(block: dict[str, Any], *, _depth: int, _max_chars: int) -> str:
    """Pull user-visible text from one provider content block dict; ignore signatures / thinking."""
    btype = str(block.get("type") or "").lower()
    if btype in (
        "thinking",
        "thought",
        "thought_signature",
        "redacted_thinking",
        "signature",
        "image_url",
        "image",
    ):
        return ""
    for key in ("text", "output_text", "output"):
        v = block.get(key)
        if isinstance(v, str) and v.strip():
            return _clip_text(v.strip(), _max_chars)
    nested = block.get("content")
    if isinstance(nested, str) and nested.strip():
        return _clip_text(nested.strip(), _max_chars)
    if isinstance(nested, (list, dict)):
        return _normalize_message_content_for_display(nested, _depth=_depth + 1, _max_chars=_max_chars)
    return ""


def _normalize_message_content_for_display(
    obj: Any,
    *,
    _depth: int = 0,
    _max_chars: int,
) -> str:
    """Recursively extract display-safe text from LangChain message content (any common provider shape)."""
    if _depth > 16:
        return ""
    if obj is None:
        return ""
    if isinstance(obj, str):
        return _clip_text(obj, _max_chars)
    if isinstance(obj, (bytes, bytearray)):
        return _clip_text(obj.decode("utf-8", errors="replace"), _max_chars)
    if isinstance(obj, (int, float, bool)):
        return _clip_text(str(obj), min(256, _max_chars))
    if isinstance(obj, tuple):
        obj = list(obj)
    if isinstance(obj, list):
        parts: list[str] = []
        used = 0
        for item in obj:
            if used >= _max_chars:
                break
            chunk = _normalize_message_content_for_display(item, _depth=_depth + 1, _max_chars=_max_chars - used)
            if chunk:
                parts.append(chunk)
                used += len(chunk)
        return _clip_text("".join(parts), _max_chars)
    if isinstance(obj, dict):
        # Nested containers (OpenAI / LC variants)
        parts_val = obj.get("parts")
        if isinstance(parts_val, list):
            return _normalize_message_content_for_display(parts_val, _depth=_depth + 1, _max_chars=_max_chars)
        # Block-shaped dict (Gemini 3+: type + text + extras.signature)
        if any(k in obj for k in ("type", "text", "output_text", "output")):
            got = _text_from_content_block_dict(obj, _depth=_depth, _max_chars=_max_chars)
            if got:
                return got
        nested = obj.get("content")
        if isinstance(nested, (str, list, dict)):
            return _normalize_message_content_for_display(nested, _depth=_depth + 1, _max_chars=_max_chars)
        # Unknown dict: never str(dict) — may include megabyte signatures
        return ""
    # Unknown atom (e.g. object instance): do not repr — fail safe
    return ""


def extract_text_from_ai_message(message: Any, *, max_chars: int | None = None) -> str:
    """Extract user-visible assistant text from a LangChain BaseMessage or raw content value.

    Gemini 3+ may return ``content`` as a list of blocks with ``extras.signature``; OpenAI may use
    string or list-of-blocks. This helper is defensive across providers and versions.
    """
    cap = max_chars if max_chars is not None else _DEFAULT_MAX_ASSISTANT_TEXT_CHARS
    if message is None:
        return ""
    raw: Any = getattr(message, "content", message)
    return _normalize_message_content_for_display(raw, _depth=0, _max_chars=cap)


def get_llm(
    provider: str | None = None,
    model: str | None = None,
    temperature: float | None = None,
    stage: str | None = None,
) -> Any:
    """Return a chat model instance for the configured provider."""
    selected_provider = (provider or _resolve_stage_provider(stage)).strip().lower()
    selected_temperature = DEFAULT_LLM_TEMPERATURE if temperature is None else temperature
    selected_timeout = DEFAULT_LLM_TIMEOUT_S

    resolved_model = model or _resolve_stage_model(selected_provider, stage)

    if selected_provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        logging.getLogger("langchain_google_genai._function_utils").disabled = True

        api_key = _require_env_any(["GEMINI_API_KEY", "GOOGLE_API_KEY"])
        return ChatGoogleGenerativeAI(
            model=resolved_model or DEFAULT_GEMINI_MODEL,
            temperature=selected_temperature,
            max_retries=6,
            timeout=selected_timeout,
            google_api_key=api_key,
        )

    if selected_provider == "openai":
        from langchain_openai import ChatOpenAI

        _require_env_any(["OPENAI_API_KEY"])
        return ChatOpenAI(
            model=resolved_model or DEFAULT_OPENAI_MODEL,
            temperature=selected_temperature,
            max_retries=2,
            timeout=selected_timeout,
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


def structured_invoke(
    llm: Any,
    messages: list[Any],
    schema: type[TModel],
    trace_label: str | None = None,
) -> TModel:
    """Invoke LLM with structured output mapped to a Pydantic schema."""
    if trace_label:
        model_name = (
            getattr(llm, "model_name", None)
            or getattr(llm, "model", None)
            or getattr(llm, "model_id", None)
            or "?"
        )
        retries = getattr(llm, "max_retries", "?")
        print(
            f"       llm[{trace_label}] invoke start model={model_name} max_retries={retries}",
            file=sys.stderr,
            flush=True,
        )
    t0 = time.time()
    try:
        from langchain_openai import ChatOpenAI

        if isinstance(llm, ChatOpenAI):
            # Avoid OpenAI "json_schema" strict mode (requires additionalProperties:false
            # everywhere); function calling is more tolerant of nested models.
            try:
                out = llm.with_structured_output(schema, method="function_calling").invoke(messages)
            except Exception as e:
                if trace_label:
                    print(
                        f"       llm[{trace_label}] invoke failed after {time.time()-t0:.1f}s ({type(e).__name__}: {e})",
                        file=sys.stderr,
                        flush=True,
                    )
                raise
            if trace_label:
                print(
                    f"       llm[{trace_label}] invoke ok {time.time()-t0:.1f}s",
                    file=sys.stderr,
                    flush=True,
                )
            return out
    except ImportError:
        pass
    try:
        out = llm.with_structured_output(schema).invoke(messages)
    except Exception as e:
        if trace_label:
            print(
                f"       llm[{trace_label}] invoke failed after {time.time()-t0:.1f}s ({type(e).__name__}: {e})",
                file=sys.stderr,
                flush=True,
            )
        raise
    if trace_label:
        print(
            f"       llm[{trace_label}] invoke ok {time.time()-t0:.1f}s",
            file=sys.stderr,
            flush=True,
        )
    return out

