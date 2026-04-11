# Example: quick coach and judge interaction context

[← Wiki home](../README.md) · [Context systems](../context-systems.md) (§4–5)

## Quick coach: gating on story map

[`document_state_has_story_map`](../../../src/narrative_dag/store/run_store.py) returns true when persisted `DocumentState` has enough **plot** or **character** signal for short advice paths. The service uses this before building a [`ContextBundle`](../../../src/narrative_dag/schemas.py) for quick coach.

## Slim narrative from a bundle

[`slim_narrative_text_from_bundle`](../../../src/narrative_dag/nodes/quick_coach.py) builds a `dict` shaped like pipeline state, calls [`build_prompt_context`](../../../src/narrative_dag/prompt_context.py) + [`format_prompt_context`](../../../src/narrative_dag/prompt_context.py), then appends a **latest critic panel** block when `critic_result` is present:

```python
# Conceptual structure (not stored verbatim in DB)
narrative = format_prompt_context(prompt_context_or_fallback) + _format_latest_critic_panel(bundle)
```

That string is wrapped by [`quick_coach_prompt`](../../../src/narrative_dag/prompts/quick_coach.py) and sent as a **single** structured LLM call (`QuickCoachAdvice`).

## Quick coach → story chat

When the API appends quick-coach output to Inkblot, turns appear in `story_chat_turns` with manifests like:

```json
{"source": "quick_coach", "chunk_id": "982b00d7-105c-4f6b-ad04-7c657bfddcc8"}
```

and assistant follow-ups may include `"follows": { "source": "quick_coach", "chunk_id": "…" }` (sample from local DB, 2026-04-08).

## Judge interaction: `_bundle_text`

[`judge_explainer`](../../../src/narrative_dag/nodes/interaction.py) / [`judge_reconsideration`](../../../src/narrative_dag/nodes/interaction.py) do **not** use chat history. They call `_bundle_text(bundle)`, which:

1. Builds a `PromptContext` from the bundle’s `context_window` + `document_state` (mirroring [`format_prompt_context`](../../../src/narrative_dag/prompt_context.py) fields).
2. Appends **repr**-style dumps of `detector_results`, `critic_result`, `defense_result`, and `current_judgment`.

Illustrative tail (structure only):

```text
…
Detectors: { ... }
Critic: { 'verdict': ..., 'critique': ..., ... }
Defense: { ... }
Current judgment: { 'decision': ..., 'evidence_spans': [...], ... }
```

That blob is passed into [`explain_prompt`](../../../src/narrative_dag/prompts/interaction.py) or [`reconsider_prompt`](../../../src/narrative_dag/prompts/interaction.py) together with the user message.

## Related code

- [`quick_coach.py`](../../../src/narrative_dag/nodes/quick_coach.py)
- [`interaction.py`](../../../src/narrative_dag/nodes/interaction.py)
- [`quick_coach_story_chat.py`](../../../src/narrative_dag/quick_coach_story_chat.py)
