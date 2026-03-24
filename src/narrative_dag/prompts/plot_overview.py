"""Plot overview prompt."""

from __future__ import annotations

from narrative_dag.prompts.editorial_policy import editorial_policy_block, stage_role_block


def plot_overview_prompt(document_text: str, genre: str) -> str:
    return (
        stage_role_block(
            "a developmental editor creating global story context",
            [
                "Infer the story's governing pressure, stakes, and thematic spine",
                "Honor the declared genre rather than generic literary expectations",
                "Keep the summary concise, concrete, and useful for downstream judgment",
            ],
        )
        + editorial_policy_block()
        + f"\nGenre intention: {genre}\n\nDocument:\n{document_text}\n"
    )

