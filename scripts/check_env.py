#!/usr/bin/env python3
"""Lightweight check that .env has the right keys for the chosen LLM provider."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate .env for Editr LLM keys.")
    parser.add_argument(
        "--env-file",
        type=Path,
        default=Path(".env"),
        help="Path to .env (default: ./.env)",
    )
    parser.add_argument(
        "--docker",
        action="store_true",
        help="Warn if EDITR_DB_PATH looks like a bare relative path (Docker volume footgun).",
    )
    args = parser.parse_args()

    if not args.env_file.is_file():
        print(f"Missing {args.env_file} — copy .env.example and fill keys.", file=sys.stderr)
        return 2

    load_dotenv(args.env_file, override=False)

    provider = (os.getenv("LLM_PROVIDER") or "gemini").strip().lower()
    openai_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    gemini_key = (os.getenv("GEMINI_API_KEY") or "").strip()
    google_key = (os.getenv("GOOGLE_API_KEY") or "").strip()
    db_path = (os.getenv("EDITR_DB_PATH") or "").strip()

    ok = True
    print(f"LLM_PROVIDER={provider!r}")

    if provider == "openai":
        if not openai_key:
            print("FAIL: OPENAI_API_KEY is empty but LLM_PROVIDER=openai")
            ok = False
        else:
            print("PASS: OPENAI_API_KEY is set")
    elif provider == "gemini":
        if not gemini_key and not google_key:
            print("FAIL: GEMINI_API_KEY and GOOGLE_API_KEY are both empty but LLM_PROVIDER=gemini")
            ok = False
        else:
            print("PASS: GEMINI_API_KEY or GOOGLE_API_KEY is set")
    else:
        print(f"WARN: LLM_PROVIDER {provider!r} is not openai|gemini — beta path may coerce; check config.")

    if args.docker and db_path:
        is_windows_abs = len(db_path) >= 3 and db_path[1] == ":" and db_path[2] in "\\/"
        if not db_path.startswith("/") and not is_windows_abs:
            print(
                "WARN: EDITR_DB_PATH looks like a relative/local path. "
                "With Docker + a /app/data volume, use /app/data/editr.sqlite or omit EDITR_DB_PATH.",
            )

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
