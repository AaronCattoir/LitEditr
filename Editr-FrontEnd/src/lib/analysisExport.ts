/**
 * Serialize story-wide analysis + chunk judgments to a single Markdown document (client download).
 */

import type { EditorialReportPayload, StoryWidePayload } from './api';

function safeFilenamePart(s: string): string {
  return s.replace(/[^\w\-]+/g, '_').replace(/_+/g, '_').slice(0, 80) || 'story';
}

export function buildStoryAnalysisMarkdown(opts: {
  title: string;
  documentId?: string;
  revisionId?: string;
  runId?: string | null;
  analysisKind?: string | null;
  report: EditorialReportPayload | null;
}): string {
  const { title, documentId, revisionId, runId, analysisKind, report } = opts;
  const lines: string[] = [];
  lines.push(`# Story analysis: ${title || 'Untitled'}`);
  lines.push('');
  lines.push('## Run metadata');
  if (documentId) lines.push(`- **Document id:** ${documentId}`);
  if (revisionId) lines.push(`- **Revision id:** ${revisionId}`);
  if (runId) lines.push(`- **Run id:** ${runId}`);
  if (analysisKind) lines.push(`- **Analysis kind:** ${analysisKind}`);
  lines.push('');

  if (!report) {
    lines.push('_No analysis report loaded._');
    return lines.join('\n');
  }

  lines.push('## Document summary');
  lines.push('');
  lines.push(report.document_summary || '_—_');
  lines.push('');

  const sw = report.story_wide;
  if (sw) {
    lines.push(...formatStoryWideSections(sw));
  }

  const cj = [...report.chunk_judgments].sort((a, b) => a.position - b.position);
  lines.push('## Section judgments');
  lines.push('');
  if (cj.length === 0) {
    lines.push('_No chunk judgments._');
  } else {
    for (const e of cj) {
      const j = e.judgment;
      lines.push(`### Position ${e.position} — \`${e.chunk_id}\``);
      lines.push('');
      lines.push(`- **Decision:** ${j.decision}`);
      lines.push(`- **Severity:** ${j.severity}`);
      lines.push(`- **Core issue:** ${j.core_issue || '—'}`);
      lines.push('');
      lines.push('**Guidance**');
      lines.push('');
      lines.push(j.guidance || '—');
      lines.push('');
    }
  }

  return lines.join('\n');
}

function formatStoryWideSections(sw: StoryWidePayload): string[] {
  const out: string[] = [];
  out.push('## Story-wide analysis');
  out.push('');

  out.push('### Plot overview');
  out.push('');
  out.push(sw.plot_overview ? jsonBlock(sw.plot_overview) : '_—_');
  out.push('');

  out.push('### Character database');
  out.push('');
  out.push(sw.character_database ? jsonBlock(sw.character_database) : '_—_');
  out.push('');

  out.push('### Narrative map');
  out.push('');
  out.push(sw.narrative_map?.length ? jsonBlock(sw.narrative_map) : '_—_');
  out.push('');

  out.push('### Emotional curve');
  out.push('');
  out.push(sw.emotional_curve?.length ? jsonBlock(sw.emotional_curve) : '_—_');
  out.push('');

  out.push('### Voice baseline');
  out.push('');
  out.push(sw.voice_baseline ? jsonBlock(sw.voice_baseline) : '_—_');
  out.push('');

  return out;
}

function jsonBlock(obj: unknown): string {
  return '```json\n' + JSON.stringify(obj, null, 2) + '\n```';
}

export function downloadMarkdownFile(filename: string, markdown: string): void {
  const blob = new Blob([markdown], { type: 'text/markdown;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

/** Plain-text download (e.g. full manuscript from Settings). */
export function downloadTextFile(filename: string, text: string, mime = 'text/plain;charset=utf-8'): void {
  const blob = new Blob([text], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export function defaultStoryAnalysisFilename(opts: {
  title: string;
  documentId?: string;
  revisionId?: string;
}): string {
  const part = safeFilenamePart(opts.title || opts.documentId || 'analysis');
  const rev = opts.revisionId ? `-${opts.revisionId.slice(0, 8)}` : '';
  return `story-analysis-${part}${rev}.md`;
}

export function defaultStoryManuscriptFilename(opts: { title: string; documentId?: string }): string {
  const part = safeFilenamePart(opts.title || opts.documentId || 'manuscript');
  return `manuscript-${part}.md`;
}
