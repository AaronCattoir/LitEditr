"""Interaction prompts."""

from __future__ import annotations

from narrative_dag.prompts.editorial_policy import editorial_policy_block, stage_role_block


def explain_prompt(context_bundle_text: str, user_message: str) -> str:
    return (
        stage_role_block(
            "the editorial judge explaining an existing decision",
            [
                "Explain the reasoning using the same preservation-vs-intervention philosophy as the main pipeline",
                "Do not invent new evidence or rewritten prose",
            ],
        )
        + editorial_policy_block()
        + "\nContext bundle:\n"
        + context_bundle_text
        + "\n\nUser question:\n"
        + user_message
    )


def reconsider_prompt(context_bundle_text: str, user_message: str) -> str:
    return (
        stage_role_block(
            "the editorial judge reconsidering a prior decision",
            [
                "Preserve the original judgment unless new reasoning shows it is too harsh or too lenient",
                "Weigh intentionality, voice logic, and genre payoff before changing the verdict",
                "Return updated advisory judgment only",
            ],
        )
        + editorial_policy_block()
        + "\nContext bundle:\n"
        + context_bundle_text
        + "\n\nUser request:\n"
        + user_message
    )
