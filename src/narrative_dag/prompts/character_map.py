"""Character mapping prompt."""

from __future__ import annotations

from narrative_dag.prompts.editorial_policy import editorial_policy_block, stage_role_block


def character_map_prompt(document_text: str, genre: str, plot_summary: str, story_point: str) -> str:
    return (
        stage_role_block(
            "a continuity editor building a canonical character map for the full document",
            [
                "Resolve aliases and nicknames to a stable canonical character identity",
                "Capture only characters that materially appear in the text",
                "When uncertain, use conservative notes rather than inventing facts",
            ],
        )
        + editorial_policy_block()
        + f"\nGenre intention: {genre}\n"
        + f"Plot summary: {plot_summary}\n"
        + f"Story point: {story_point}\n\n"
        + "Return structured character database only.\n\n"
        + f"Document:\n{document_text}\n"
    )
