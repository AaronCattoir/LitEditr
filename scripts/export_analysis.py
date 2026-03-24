"""Export an analysis run from SQLite to a markdown report."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

DB = "artifacts/runtime.sqlite"

SEVERITY_LABEL = {1: "Minor", 2: "Low", 3: "Medium", 4: "High", 5: "Critical"}
DECISION_EMOJI = {"rewrite": "🔴", "revise": "🟡", "keep": "🟢", "flag": "🟠"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export analysis run to markdown")
    parser.add_argument("--db", default=DB, help="SQLite database path")
    parser.add_argument("--run-id", default=None, help="Specific run_id to export")
    parser.add_argument("--genre", default=None, help="Filter auto-selected run by genre")
    parser.add_argument("--out", default=None, help="Output markdown path")
    parser.add_argument(
        "--allow-incomplete",
        action="store_true",
        help="Allow exporting latest run even if document_state is not saved yet",
    )
    parser.add_argument(
        "--prefer-latest",
        action="store_true",
        help="Prefer newest run by created_at (even if incomplete) when selecting automatically",
    )
    return parser.parse_args()


def _select_run_id(
    conn: sqlite3.Connection,
    run_id: str | None,
    genre: str | None,
    allow_incomplete: bool,
    prefer_latest: bool,
) -> str:
    cur = conn.cursor()
    if run_id:
        cur.execute("select 1 from runs where run_id=?", (run_id,))
        if not cur.fetchone():
            raise RuntimeError(f"Run not found: {run_id}")
        return run_id

    where = []
    params: list[object] = []
    if genre:
        where.append("r.genre = ?")
        params.append(genre)

    if not prefer_latest:
        # Prefer completed runs (document_state saved at end of analyze_document).
        completion_join = "inner join run_document_state ds on ds.run_id = r.run_id"
        query = f"""
            select r.run_id, r.created_at, count(rc.chunk_id) as n
            from runs r
            {completion_join}
            left join run_chunks rc on rc.run_id = r.run_id
            {'where ' + ' and '.join(where) if where else ''}
            group by r.run_id
            order by r.created_at desc
            limit 1
        """
        cur.execute(query, params)
        row = cur.fetchone()
        if row:
            return row["run_id"]

    if not allow_incomplete:
        g = f" for genre '{genre}'" if genre else ""
        raise RuntimeError(
            f"No completed runs found{g}. Run with --allow-incomplete to export latest partial run."
        )

    # Fallback: newest run by created_at (possibly still in-flight).
    query = f"""
        select r.run_id
        from runs r
        {'where ' + ' and '.join(where) if where else ''}
        order by r.created_at desc
        limit 1
    """
    cur.execute(query, params)
    row = cur.fetchone()
    if not row:
        g = f" for genre '{genre}'" if genre else ""
        raise RuntimeError(f"No runs found{g}.")
    return row["run_id"]


def _load_doc_summary(conn: sqlite3.Connection, run_id: str) -> str:
    cur = conn.cursor()
    cur.execute("select payload_json from run_document_state where run_id=?", (run_id,))
    row = cur.fetchone()
    if not row:
        return "No document-level summary available yet."
    payload = json.loads(row["payload_json"])
    plot = payload.get("plot_overview") or {}
    story_point = (plot.get("story_point") or "").strip()
    if story_point:
        return story_point
    plot_summary = (plot.get("plot_summary") or "").strip()
    if plot_summary:
        return plot_summary
    return "No document-level summary available yet."


def main() -> None:
    args = parse_args()
    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    run_id = _select_run_id(
        conn,
        args.run_id,
        args.genre,
        args.allow_incomplete,
        args.prefer_latest,
    )

    cur.execute(
        "select chunk_id, position, payload_json from run_chunks where run_id=? order by position",
        (run_id,),
    )
    chunks = [(row["chunk_id"], row["position"], json.loads(row["payload_json"])) for row in cur.fetchall()]

    cur.execute(
        "select chunk_id, judgment_json from judgment_versions where run_id=? order by chunk_id, version desc",
        (run_id,),
    )
    judgments: dict[str, dict] = {}
    for row in cur.fetchall():
        if row["chunk_id"] not in judgments:
            judgments[row["chunk_id"]] = json.loads(row["judgment_json"])
    doc_summary = _load_doc_summary(conn, run_id)

    lines: list[str] = []

    cur.execute("select genre from runs where run_id=?", (run_id,))
    genre_row = cur.fetchone()
    genre_display = (genre_row["genre"] if genre_row else "unknown").replace("_", " ").title()
    conn.close()

    out = args.out or f"artifacts/analysis_{run_id[:8]}.md"

    lines += [
        "# Editorial Analysis Report",
        "",
        "**Story:** *Lanky Kong* (working title)  ",
        f"**Genre:** {genre_display}  ",
        f"**Run ID:** `{run_id}`  ",
        f"**Sections:** {len(chunks)}  ",
        "**Model:** Vertex AI (gemini-3.1-pro-preview)",
        "",
        "## Document Summary",
        "",
        f"> {doc_summary}",
        "",
        "---",
        "",
        "## Section-by-Section Results",
        "",
    ]

    for cid, pos, payload in chunks:
        j = payload.get("current_judgment", {})
        det = payload.get("detector_results", {})
        critic = payload.get("critic_result", {})
        defense = payload.get("defense_result", {})
        el = judgments.get(cid, {})
        text = payload["target_chunk"]["text"]

        decision = j.get("decision", "?")
        severity_raw = j.get("severity", 0)
        severity_num = int(float(severity_raw)) if severity_raw else 0
        severity_label = SEVERITY_LABEL.get(severity_num, str(severity_raw))
        is_drift = j.get("is_drift", False)

        emoji = DECISION_EMOJI.get(decision, "⚪")

        excerpt = text.strip().lstrip("~").strip()[:300].replace("\n", " ")

        lines += [
            f"### {emoji} Section {pos + 1} ({cid})",
            "",
            f"**Decision:** `{decision.upper()}` | **Severity:** {severity_num}/5 ({severity_label}) | **Drift detected:** {'Yes' if is_drift else 'No'}",
            "",
            f"> *\"{excerpt}...\"*",
            "",
        ]

        if j.get("core_issue"):
            lines += [f"**Core Issue:** {j['core_issue']}", ""]

        lines += [
            f"**Reasoning:**",
            f"{j.get('reasoning', '—')}",
            "",
            f"**Guidance:**",
            f"{j.get('guidance', '—')}",
            "",
        ]

        # Detector flags
        d_flags: list[str] = []
        drift = det.get("drift") or {}
        if drift.get("drift_score", 0) > 0.3:
            d_flags.append(
                f"**Drift** score {drift['drift_score']:.2f} ({drift.get('drift_type','?')}): {drift.get('evidence','')}"
            )
        cliche_r = det.get("cliche") or {}
        if cliche_r.get("cliche_flags"):
            flags = " | ".join(f"`{f}`" for f in cliche_r["cliche_flags"][:6])
            d_flags.append(f"**Clichés** (severity {cliche_r.get('severity', 0):.1f}): {flags}")
        vague_r = det.get("vagueness") or {}
        if vague_r.get("vague_phrases"):
            phrases = " | ".join(f"`{v}`" for v in vague_r["vague_phrases"][:5])
            d_flags.append(f"**Vague phrases** ({vague_r.get('impact','?')} impact): {phrases}")
        redundancy_r = det.get("redundancy") or {}
        if redundancy_r.get("redundant_with"):
            d_flags.append(f"**Redundancy** ({redundancy_r.get('type','?')}): overlaps with {redundancy_r['redundant_with']}")
        risk_r = det.get("risk") or {}
        if risk_r.get("risk_type") and risk_r.get("risk_type") not in ("none", ""):
            d_flags.append(f"**Risk** ({risk_r['risk_type']}): payoff — {risk_r.get('payoff','?')}")
        eh_r = det.get("emotional_honesty") or {}
        if eh_r.get("mismatch"):
            d_flags.append(
                f"**Emotional mismatch**: expected `{eh_r.get('expected_emotion','?')}`, text signals `{eh_r.get('actual_text_signal','?')}`"
            )

        if d_flags:
            lines += ["**Detector Flags:**"]
            for f in d_flags:
                lines.append(f"- {f}")
            lines.append("")

        # Critic / Defense
        if critic.get("critique"):
            lines += [
                f"**Critic:** {critic['critique']}",
                "",
            ]
        if defense.get("defense"):
            lines += [
                f"**Defense:** {defense['defense']}",
                "",
            ]

        if el.get("is_intentional_deviation"):
            lines += [
                f"> **Elasticity override:** {el.get('justification', '')}",
                "",
            ]

        lines += ["---", ""]

    # Summary table
    lines += [
        "## Summary Table",
        "",
        "| Section | Decision | Severity | Drift | Core Issue |",
        "|---------|----------|----------|-------|------------|",
    ]
    for cid, pos, payload in chunks:
        j = payload.get("current_judgment", {})
        decision = j.get("decision", "?")
        severity_raw = j.get("severity", 0)
        severity_num = int(float(severity_raw)) if severity_raw else 0
        is_drift = j.get("is_drift", False)
        core = (j.get("core_issue") or "").replace("|", "/")
        if len(core) > 90:
            core = core[:87] + "..."
        emoji = DECISION_EMOJI.get(decision, "⚪")
        drift_yn = "Yes" if is_drift else "No"
        lines.append(f"| {emoji} {cid} | `{decision}` | {severity_num}/5 | {drift_yn} | {core} |")

    lines += [
        "",
        "---",
        "",
        "_Generated by editr narrative analysis pipeline._",
    ]

    md = "\n".join(lines)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(md, encoding="utf-8")
    print(f"run_id={run_id}")
    print(f"Written to {out}  ({len(md):,} chars, {len(lines)} lines)")


if __name__ == "__main__":
    main()
