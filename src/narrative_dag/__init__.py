"""Narrative analysis DAG: advisory-only editorial judgments for long-form text."""

from __future__ import annotations

import warnings

warnings.filterwarnings(
    "ignore",
    message=r"Core Pydantic V1 functionality isn't compatible with Python 3\.14 or greater\.",
    category=UserWarning,
)
warnings.filterwarnings(
    "ignore",
    message=r"The class `ChatVertexAI` was deprecated in LangChain 3\.2\.0.*",
    category=Warning,
)

__version__ = "0.1.0"
