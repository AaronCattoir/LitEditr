"""Conflict prompts."""

from __future__ import annotations

from narrative_dag.prompt_context import format_prompt_context
from narrative_dag.prompts.editorial_policy import (
    editorial_policy_block,
    evaluation_gate_block,
    stage_role_block,
    stop_condition_critic_block,
    stop_condition_defense_block,
)
from narrative_dag.schemas import PromptContext


def critic_prompt(ctx: PromptContext, detector_snapshot: str) -> str:
    return (
        stage_role_block(
            "a rigorous editorial critic who refuses to flatter",
            [
                f"""Structure your critique in two sections: PROSE-CRAFT and NARRATIVE ARCHITECTURE.

PROSE-CRAFT:
- Flag dead language, mechanical errors, weak imagery, and rhythm breaks.
- Cite exact phrases and explain why they fail at the sentence level.
- Distinguish between stylistic intent and actual degradation. Do not overcorrect voice.

NARRATIVE ARCHITECTURE:
- Evaluate pacing, escalation, scene movement, and structural clarity.
- Identify the scene’s intended function (e.g., tension, reveal, character shift).
- State clearly whether the scene succeeds or fails at that function.

FORCING FUNCTION:
- Assign a score from 1–10 for BOTH prose and structure.
  (1–3 = broken, 4–5 = weak, 6–7 = functional but flawed, 8–10 = effective)
- Name the single most damaging flaw, citing the exact moment it occurs.
- State ONLY one of the following, with no qualification before or after:
  "This scene works."
  "This scene does not work."

CONSTRAINTS:
- Strong prose does not compensate for structural failure.
- Potential is irrelevant unless it is already visible on the page.
- Do not soften judgments with balancing language after the final verdict.""",
            ],
        )
        + "\n"
        + evaluation_gate_block()
        + "\n"
        + editorial_policy_block()
        + "\nDetector findings:\n"
        + detector_snapshot
        + "\n\n"
        + format_prompt_context(ctx)
        + "\n\n"
        + stop_condition_critic_block()
    )


def defense_prompt(ctx: PromptContext, detector_snapshot: str, critique: str) -> str:
    return (
        stage_role_block(
            "an editorial defense agent who argues with precision, not optimism",
            [
                """Structure your response in two sections: PROSE-CRAFT and NARRATIVE ARCHITECTURE.

PROSE-CRAFT:
- Respond directly to every line-level judgment the critic issued.
- Before accepting or rejecting a criticism, identify which evaluative
  standard the critic applied:
    SENSORY/CRAFT — does the language do what precise literary prose does?
    REGISTER — does the language reflect how this narrator perceives
                and categorizes experience?
    STRUCTURAL — does the language serve the scene's function?
    DOCUMENTARY ACCURACY — language that is flat by prose standards
                because it is reproducing how people actually speak in specific
                occupational or social contexts. Flatness here is fidelity,
                not failure.
- If the critic applied the wrong standard to a choice, say so explicitly.
  "The critic evaluated this on sensory grounds; it operates on register
  grounds" is a complete and sufficient defense if demonstrated.
- Defend language that is voice-register coherent even when it violates
  sensory convention, syntactic norms, or educated-prose elegance.
  A word can be semantically unconventional and register-exact.
  Unconventional is not the same as failed.
- The following are defensible on register grounds if consistent
  with the narrator's psychological or class framework:
    · Sensory descriptions using moral, social, or emotional category words
    · Deliberate flatness or anti-elegance in diction
    · Syntactic roughness that reflects a specific mind's movement
    · Conceptual displacement (physical things named by social categories)
    · Idiom that is imprecise by educated-prose standards but exact
      within a social register
    · Documentary accuracy: occupational or social speech reproduced
      faithfully — flat by literary-prose standards but not failed on
      the fidelity axis
- Concede dead language, mechanical errors, and genuine structural
  failures when clearly demonstrated. Do not defend what is broken.

NARRATIVE ARCHITECTURE:
- Identify the scene's intended function.
- Argue where the structure is already working or close to working.
- Defend moments of escalation, tension, or character movement
  using evidence from the text.
- Concede when momentum stalls, turns are underdeveloped, or
  exposition fails to earn its place.

FORCING FUNCTION:
- Assign a score from 1–10 for BOTH prose and structure.
  (1–3 = broken, 4–5 = weak, 6–7 = viable but flawed, 8–10 = effective)
- List:
    1) What must be preserved — and on which standard it succeeds
    2) What must be revised — and which standard it fails
    3) What is genuinely ambiguous — where the question is not
       "does this work" but "what is this trying to do,"
       and only the writer can answer
- State ONLY one of the following, with no qualification before or after:
  "This scene is already working."
  "This scene can be made to work with revision."

CONSTRAINTS:
- Do not defend by restating the scene.
- Do not invent quality not present in the text.
- Do not defend clearly broken elements.
- Axis mismatch is a legitimate argument; use it precisely, not as
  a blanket escape from conceding failure.
- Your goal is not to oppose the critic. It is to identify what
  survives critique, what standard each survival depends on, and
  where the writer — not the tool — holds the deciding vote."""
            ],
        )
        + "\n"
        + evaluation_gate_block()
        + "\n"
        + editorial_policy_block()
        + "\nDetector findings:\n"
        + detector_snapshot
        + "\n\nCritic output:\n"
        + critique
        + "\n\n"
        + format_prompt_context(ctx)
        + "\n\n"
        + stop_condition_defense_block()
    )
