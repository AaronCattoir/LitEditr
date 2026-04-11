# Example: pipeline `ContextWindow` and prompt-shaped text

[← Wiki home](../README.md) · [Context systems](../context-systems.md) (§1)

## Provenance

**Sample from local `editr.sqlite` (captured 2026-04-08):**

- `run_id`: `c03c1700-b1c1-4599-87b6-4b5fd475ff40`
- `chunk_id`: `005933ac-7302-4388-a04f-f71db4bf0b5e` (first chunk in run order)

The same payload lives in SQLite table `run_chunks` (`payload_json`), merged during analysis. [`RunStore.get_chunk_artifact`](../../../src/narrative_dag/store/run_store.py) returns this object.

## `context_window` (persisted slice)

The artifact includes `context_window` with `global_summary`, `previous_chunks`, `next_chunks`, and `target_chunk`. For this chunk, neighbors are asymmetric (first chunk in the partition):

```json
{
  "context_window": {
    "global_summary": "In a dystopian society, a dutiful worker named Morgan, tasked with 'feeding' a mysterious Wall, becomes envious when his friend Jeremiha is chosen for 'ascension.' Driven by curiosity, Morgan opens one of the cylinders he's meant to deliver, discovering a living fetus. This transgression leads the Wall to demand a horrific atonement: Morgan is caged with his wife, Abigail, and forced by the Wall's will to cannibalize her as a public sacrifice.",
    "previous_chunks": [],
    "next_chunks": [ { "id": "…", "text": "…" } ],
    "target_chunk": {
      "id": "005933ac-7302-4388-a04f-f71db4bf0b5e",
      "text": "<<<EDITR_CHAPTER id=\"ee7a60ca-4ce4-4fb4-bc55-921859bd2985\" title=\"Short\">>>\nThe squeal of worn rattling wheels dwelled and droned into my drifting attention. In this moment, as so many before, my task took its own pace leaving me as just another system in its completion. My cart, save for the noise, hovered steadily ac…"
    }
  }
}
```

(On this sample row, `previous_chunks` is empty and `next_chunks` has length 1; `text` values are truncated here for readability.)

Full `target_chunk.text` in the DB is ~5373 characters for this row.

## How this becomes prompt text

During a live run, [`build_prompt_context`](../../../src/narrative_dag/prompt_context.py) builds a `PromptContext` from graph state; [`format_prompt_context`](../../../src/narrative_dag/prompt_context.py) renders the **NARRATIVE CONTEXT** block plus **PREVIOUS / TARGET / NEXT** chunk bodies. The rendered string is not stored verbatim in SQLite; the **structured** `context_window` and `document_state` fields are what get persisted.

Illustrative excerpt (structure only—plot copy matches the sample above):

```
NARRATIVE CONTEXT
Primary genre: …
Story point: …
Plot summary: In a dystopian society, a dutiful worker named Morgan…
…
PREVIOUS CONTEXT (reference only — do not critique)
(none)

TARGET CHUNK ← critique this chunk only
<<<EDITR_CHAPTER …>>>
The squeal of worn rattling wheels…

NEXT CONTEXT (reference only — do not critique)
…
```

## Related code

- [`build_context_window`](../../../src/narrative_dag/nodes/ingestion.py)
- [`run_context_builder`](../../../src/narrative_dag/nodes/ingestion.py)
