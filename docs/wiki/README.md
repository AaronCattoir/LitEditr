# Editr documentation wiki

Internal reference for how **context** is built, persisted, and consumed across the narrative pipeline, Inkblot story chat, quick coach, judge interaction, evidence, and the SPA.

## Context systems

- **[Context systems (full map)](./context-systems.md)** — All seven stacks, orchestration notes, and comparison table.

## Worked examples

Each page uses **real snippets from `editr.sqlite`** when available (with provenance). Empty databases get **synthetic** shapes that match the code.

1. [Pipeline: `ContextWindow` and prompt text](./examples/01-pipeline-context-window.md)
2. [Persisted bundles and story-wide JSON](./examples/02-persisted-bundles-and-story-wide.md)
3. [Inkblot: persona snapshots and message assembly](./examples/03-inkblot-persona-and-messages.md)
4. [Quick coach and judge interaction](./examples/04-quick-coach-and-judge-interaction.md)
5. [Evidence spans and client-side draft metadata](./examples/05-evidence-and-frontend-context.md)

## Related

- [Agent / DAG handoff](../../AGENT_CONTEXT.md) (repo root)
- [Pet soul (Inkblot seed)](../pet/PET_SOUL.md)
- [Main README](../../README.md)
