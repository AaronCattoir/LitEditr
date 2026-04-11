# Example: evidence spans and client-side context

[← Wiki home](../README.md) · [Context systems](../context-systems.md) (§6–7)

## Provenance (judgment evidence)

**Sample from local `editr.sqlite` (2026-04-08):**

- `run_id`: `c03c1700-b1c1-4599-87b6-4b5fd475ff40`
- `chunk_id`: `005933ac-7302-4388-a04f-f71db4bf0b5e`
- Table `judgment_versions` (`judgment_json`) — latest version row for that pair.

`EditorJudgment` includes `evidence_spans` with **global** character offsets into the manuscript (clamped to the chunk during normalization).

```json
[
  {
    "start_char": 2533,
    "end_char": 2608,
    "quote": " As per the common occurring within my task not all events happen to be dul",
    "label": "Word Salad / Clunky Prose"
  },
  {
    "start_char": 3599,
    "end_char": 3605,
    "quote": " sound",
    "label": "Non-word / Immersion Break"
  }
]
```

(Four spans total in this row; two shown.)

## `evidence_fill` role

[`evidence_fill`](../../../src/narrative_dag/evidence_fill.py) repairs or fills spans when the model omits structured evidence or quotes drift from the chunk text. It is **not** part of the pipeline “context window” assembly; it operates on results before the UI consumes them.

## Frontend evidence mapping

[`Editr-FrontEnd/src/lib/evidenceMapping.ts`](../../../Editr-FrontEnd/src/lib/evidenceMapping.ts) maps API evidence to editor decorations.

This is orthogonal to [`format_prompt_context`](../../../src/narrative_dag/prompt_context.py): the editor needs **positions** in the visible buffer; the LLM prompts use **chunk text** bundles from state or SQLite.

## Client draft storage (illustrative)

Not stored in SQLite. [`draftStorage.ts`](../../../Editr-FrontEnd/src/lib/draftStorage.ts) uses **localStorage** keys:

| Key pattern | Purpose |
|-------------|---------|
| `editr:draft:{documentId}` | Current `DraftPayload`: `chapters`, `activeChapterId`, `metadata` |
| `editr:draft:pending` | Unsaved cross-session pending draft (`PendingDraftPayload` + `savedAt`) |

Illustrative JSON shape:

```json
{
  "version": 1,
  "chapters": [],
  "activeChapterId": "…",
  "metadata": {
    "title": "…",
    "plot": "…",
    "scene": "…",
    "characters": []
  }
}
```

## Story-wide metadata helpers

[`storyWideMetadata.ts`](../../../Editr-FrontEnd/src/lib/storyWideMetadata.ts) derives UI fields (e.g. scene text, character list) from **client-held** `StoryWidePayload` / report payloads—**not** from `DocumentState` on the server unless the app has fetched and cached analysis results.

## Related code

- [`evidence_fill.py`](../../../src/narrative_dag/evidence_fill.py)
- [`evidenceMapping.ts`](../../../Editr-FrontEnd/src/lib/evidenceMapping.ts)
- [`draftStorage.ts`](../../../Editr-FrontEnd/src/lib/draftStorage.ts)
- [`storyWideMetadata.ts`](../../../Editr-FrontEnd/src/lib/storyWideMetadata.ts)
