"""Representation prompts."""

from __future__ import annotations

from narrative_dag.prompt_context import format_prompt_context
from narrative_dag.prompts.editorial_policy import editorial_policy_block, stage_role_block
from narrative_dag.schemas import PromptContext


def paragraph_analysis_prompt(ctx: PromptContext) -> str:
    return (
        stage_role_block(
            "a narrative analyst building a precise editorial snapshot for one chunk",
            [
                "Identify the chunk's function and authorial intent in the current story trajectory",
                "Describe voice signals without punishing deliberate first-person roughness",
                "Call out weakness only when it creates reader-facing confusion or damage",
            ],
        )
        + editorial_policy_block()
        + "\nReturn structured analysis only.\n\n"
        + format_prompt_context(ctx)
    )


def voice_profile_prompt(ctx: PromptContext, paragraph_intent: str) -> str:
    return (
        stage_role_block(
            "a voice diagnostician measuring how the passage sounds on the page",
            [
                "Describe lexical, syntactic, rhetorical, and psychological voice features",
                "Separate character/narrator idiom from accidental clumsiness",
                "Judge style in relation to the declared genre and story pressure",
            ],
        )
        + editorial_policy_block()
        + f"\nParagraph intent: {paragraph_intent}\n\n"
        + format_prompt_context(ctx)
    )


def dialogue_analysis_prompt(ctx: PromptContext) -> str:
    return (
        stage_role_block(
            "a dialogue specialist tracking character voice consistency",
            [
                "Identify whether a speaker voice is distinct and stable",
                "Treat colloquial, regional, or working-class speech as a voice asset when intentional",
                "Flag only dialogue that flattens character or breaks scene pressure",
            ],
        )
        + editorial_policy_block()
        + "\nReturn structured dialogue analysis only.\n\n"
        + format_prompt_context(ctx)
    )
