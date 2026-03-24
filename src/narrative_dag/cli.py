"""Click-based CLI entrypoint. Thin adapter over NarrativeAnalysisService."""

from __future__ import annotations

import json
from pathlib import Path

import click

from narrative_dag.contracts import AnalyzeDocumentRequest, ChatRequest
from narrative_dag.service import NarrativeAnalysisService


@click.group()
@click.option("--db", default="editr.sqlite", help="SQLite database path (default: editr.sqlite)")
@click.pass_context
def cli(ctx, db: str):
    ctx.ensure_object(dict)
    ctx.obj["db"] = db
    ctx.obj["service"] = NarrativeAnalysisService(db_path=db)


@cli.command()
@click.option("--genre", required=True, help="Genre (e.g. literary_fiction, thriller)")
@click.option("--title", default=None, help="Document title")
@click.option("--author", default=None, help="Document author")
@click.argument("input_file", type=click.Path(exists=True, path_type=Path), required=False)
@click.pass_context
def analyze(ctx, genre: str, title: str | None, author: str | None, input_file: Path | None):
    """Run narrative analysis on a document. Input: file path or stdin."""
    service: NarrativeAnalysisService = ctx.obj["service"]
    if input_file:
        text = input_file.read_text(encoding="utf-8", errors="replace")
    else:
        text = click.get_text_stream("stdin").read()
    request = AnalyzeDocumentRequest(
        document_text=text,
        genre=genre,
        title=title,
        author=author,
    )
    response = service.analyze_document(request)
    if not response.success:
        click.echo(response.error, err=True)
        raise SystemExit(1)
    out = {
        "run_id": response.run_id,
        "chunk_judgments": [e.model_dump() for e in response.report.chunk_judgments],
        "document_summary": response.report.document_summary,
    }
    click.echo(json.dumps(out, indent=2))


@cli.command()
@click.option("--run-id", required=True, help="Run ID from analyze")
@click.option("--chunk-id", required=True, help="Chunk ID (e.g. c1)")
@click.option("--mode", type=click.Choice(["explain", "reconsider"]), default="explain")
@click.argument("message", required=False)
@click.pass_context
def chat(ctx, run_id: str, chunk_id: str, mode: str, message: str | None):
    """Chat with the judge about a chunk (explain or reconsider)."""
    service: NarrativeAnalysisService = ctx.obj["service"]
    msg = message or click.prompt("Message")
    request = ChatRequest(run_id=run_id, chunk_id=chunk_id, user_message=msg, mode=mode)
    response = service.chat(request)
    if not response.success:
        click.echo(response.error, err=True)
        raise SystemExit(1)
    click.echo(response.reply)


if __name__ == "__main__":
    cli(obj={})
