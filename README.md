# editr

Advisory-only editorial analysis DAG for long-form narrative text (stories, novels). Ingests documents with user-defined genre intention, builds document state, runs detectors, performs critic/defense conflict, and delivers per-chunk editorial judgments (keep/cut/rewrite guidance) without generating replacement prose.

## Setup

```bash
pip install -e ".[dev]"
```

## Run

```bash
python -m narrative_dag.cli --help
```

## Architecture

- **Ingestion** → **Representation** → **Detection** → **Conflict** → **Judgment** → **Interaction**
- SQLite for runs, judgments, chat turns; optional Parquet export for analytics.
- CLI first; service layer is transport-agnostic for future GUI/API.

## Chunking Contract

- The ingestion step uses an LLM to split the input text into narrative-beat chunks.
- Chunk boundaries are represented as **character spans** over the original `RawDocument.text`:
  - `Chunk.start_char` (0-based, inclusive)
  - `Chunk.end_char` (0-based, end-exclusive)
- The produced chunks form a **contiguous partition** of the document (no overlaps, no gaps).
- For very long inputs (novel-sized), chunking switches to a **chapter-first** strategy:
  - detect `Chapter`/`Part` spans
  - run one-shot chunking per chapter
  - stitch chapter-local spans back into **global** `start_char`/`end_char` offsets.
