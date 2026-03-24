"""Ingestion prompts: LLM-based chunk boundary detection."""

from __future__ import annotations


def chunk_boundary_prompt(text: str, genre: str) -> str:
    """One-shot prompt to return character-span chunk boundaries.

    Important:
    - Offsets are 0-based into the exact text provided below.
    - Use end-exclusive spans: chunk_text = text[start_char:end_char].
    - Return boundaries that partition the entire text with no overlaps and no gaps.
    """
    # The delimiter makes it easier for deterministic test mocks to extract the raw text.
    return (
        "You are a developmental editor and segmentation expert.\n"
        "Your task: split the story into coherent narrative beats suitable for editorial review.\n"
        "Chunking must be by narrative beat (scene/turn/time/perspective/tonal shift), not by formatting.\n\n"
        f"Genre intention: {genre}\n\n"
        "Return a JSON object matching the provided schema with a list of chunk boundaries.\n\n"
        "Rules (strict):\n"
        "- Offsets are 0-based character indices into the exact DOCUMENT text below.\n"
        "- Use end-exclusive spans. chunk_text = text[start_char:end_char].\n"
        "- The boundaries must partition the entire document: \n"
        "  * first boundary start_char must be 0\n"
        "  * last boundary end_char must be len(text)\n"
        "  * boundaries must be non-overlapping and in ascending order\n"
        "  * there must be no gaps: every character belongs to exactly one chunk\n"
        "- Each chunk should be as small as possible while still representing a coherent editorial unit.\n\n"
        "Output each chunk with:\n"
        "- start_char\n"
        "- end_char\n"
        "- beat_label (short label like 'scene_change', 'dialogue_turn', 'time_jump', 'tonal_shift')\n\n"
        "DOCUMENT:\n"
        "<<<TEXT>>>\n"
        f"{text}\n"
        "<<<ENDTEXT>>>"
    )
