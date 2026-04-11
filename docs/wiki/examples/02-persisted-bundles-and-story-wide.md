# Example: persisted bundles and story-wide JSON

[← Wiki home](../README.md) · [Context systems](../context-systems.md) (§2)

## Provenance

**Sample from local `editr.sqlite` (2026-04-08):**

- `run_id`: `c03c1700-b1c1-4599-87b6-4b5fd475ff40`
- `run_document_state.payload_json`: one row per run in table `run_document_state`.

## `run_document_state` keys

The persisted `DocumentState` JSON includes (among others):

```text
allowed_variance, character_database, character_voice_map, emotional_curve,
genre_intention, narrative_map, plot_overview, voice_baseline
```

[`RunStore.get_document_state`](../../../src/narrative_dag/store/run_store.py) deserializes this into a `DocumentState` model.

## Story-wide API shape

[`serialize_story_wide_for_api`](../../../src/narrative_dag/store/run_store.py) projects the same logical state into API / Inkblot-friendly JSON:

- `plot_overview`
- `character_database`
- `narrative_map`
- `emotional_curve`
- `voice_baseline`

That dictionary is what [`story_wide_from_document_state`](../../../src/narrative_dag/story_chat.py) passes into the Inkblot system prompt when a run exists (subject to string caps in `_system_prompt`).

## `ContextBundle` assembly

[`RunStore.get_context_bundle(run_id, chunk_id)`](../../../src/narrative_dag/store/run_store.py) combines:

1. **Per-chunk artifact** from `run_chunks.payload_json` — must contain at least `target_chunk`; typically also `context_window`, `detector_results`, `critic_result`, `defense_result`, `current_judgment`, etc.
2. **Run-level** `document_state` from `run_document_state`.
3. **Genre** — resolved from `document_state.genre_intention` for the bundle.

So the bundle is always **run + chunk** scoped, never chat-history scoped.

## Truncated `plot_overview` sample (same run)

The stored `plot_overview` includes `plot_summary`, `story_point`, `arc_map`, `stakes`, etc. Example opening (truncated):

```json
{
  "plot_summary": "In a dystopian society, a dutiful worker named Morgan…",
  "story_point": "The story is fundamentally about the terrifying consequences of questioning an absolute, malevolent authority…",
  "arc_map": [
    { "phase": "Setup", "summary": "Morgan describes his monotonous task…" },
    { "phase": "Inciting Incident", "summary": "Jeremiha announces his 'ascension'…" }
  ],
  "stakes": "The immediate stakes are Morgan's and Abigail's lives…"
}
```

(Full JSON in DB is longer; keys vary by model output.)

## Related code

- [`ContextBundle`](../../../src/narrative_dag/schemas.py)
- [`get_context_bundle`](../../../src/narrative_dag/store/run_store.py)
