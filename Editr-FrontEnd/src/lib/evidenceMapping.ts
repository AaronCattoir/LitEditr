/**
 * Map document-level evidence spans to per-section Unicode offsets for the editor (section.content only).
 */

import type {
  ChapterDoc,
  ClientChunkSpan,
  EvidenceSpanPayload,
  GraphChunkJudgment,
  SpanSynthesisPayload,
} from './api';
import { buildChapterDelimiterLine, countCodePoints, sliceByCodePoints } from './manuscriptSerialize';

export type EvidenceSource = 'critic' | 'defense' | 'judgment';

export interface EditorEvidenceHighlight {
  /** Stable id for DOM / scroll sync */
  key: string;
  source: EvidenceSource;
  /** Inclusive start, exclusive end — Unicode code points in section.content */
  startCp: number;
  endCp: number;
  quote: string;
  /**
   * Index in punctuation/whitespace-stripped stream of section markdown up to startCp.
   * Used to pick the correct occurrence when the same quote appears twice — must match
   * the same stripping used in the editor highlight plugin.
   */
  normAnchor: number;
  bubbleTitle: string;
  bubbleBody: string;
}

const EVIDENCE_STRIP_CHAR = /[\s.,!?;:"'“”‘’()\[\]{}_*\-#]/;

/** Count non-stripped code points in section markdown before `endCp` (for tie-breaking in PM). */
function normAnchorAtCp(sectionContent: string, endCp: number): number {
  let cp = 0;
  let n = 0;
  for (const ch of sectionContent) {
    if (cp >= endCp) break;
    if (!EVIDENCE_STRIP_CHAR.test(ch)) n += 1;
    cp += 1;
  }
  return n;
}

function chapterHeaderCp(ch: ChapterDoc): number {
  return countCodePoints(buildChapterDelimiterLine(ch.id, ch.title));
}

function spanOverlapsChunk(
  span: EvidenceSpanPayload | SpanSynthesisPayload,
  c0: number,
  c1: number,
): { docStart: number; docEnd: number } | null {
  const gs = span.start_char;
  const ge = span.end_char;
  if (ge <= gs) return null;
  const is = Math.max(gs, c0);
  const ie = Math.min(ge, c1);
  if (ie <= is) return null;
  return { docStart: is, docEnd: ie };
}

function toEditorRange(
  overlap: { docStart: number; docEnd: number },
  chunkStart: number,
  headerCp: number,
  contentCpLen: number,
): { startCp: number; endCp: number } | null {
  const rel0 = overlap.docStart - chunkStart;
  const rel1 = overlap.docEnd - chunkStart;
  const ed0 = Math.max(0, rel0 - headerCp);
  const ed1 = Math.min(contentCpLen, rel1 - headerCp);
  if (ed1 <= ed0) return null;
  return { startCp: ed0, endCp: ed1 };
}

function quoteLooksStale(sectionContent: string, startCp: number, endCp: number, quote: string): boolean {
  const q = quote.trim();
  if (q.length < 4) return false;
  const slice = sliceByCodePoints(sectionContent, startCp, endCp).trim();
  if (slice === q) return false;
  const needle = q.slice(0, Math.min(24, q.length)).toLowerCase();
  if (!needle) return false;
  return !slice.toLowerCase().includes(needle);
}

function firstSentence(s: string | undefined): string {
  const t = (s ?? '').trim();
  if (!t) return '';
  const m = t.match(/(.+?[.!?])(\s|$)/);
  const out = (m?.[1] ?? t).trim();
  return out.length > 200 ? `${out.slice(0, 200).trimEnd()}…` : out;
}

function bubbleForCritic(g: GraphChunkJudgment, idx: number, span: EvidenceSpanPayload): { title: string; body: string } {
  const c = g.critic;
  const fpLine = c?.failure_points?.[idx] ?? c?.failure_points?.[0];
  const q = span.quote?.trim();
  const parts = [
    q ? `“${q.length > 400 ? `${q.slice(0, 400)}…` : q}”` : '',
    fpLine,
    c?.critique?.trim(),
  ].filter(Boolean);
  return { title: `Critic · evidence ${idx + 1}`, body: parts.join('\n\n') || '—' };
}

function bubbleForDefense(g: GraphChunkJudgment, idx: number, span: EvidenceSpanPayload): { title: string; body: string } {
  const d = g.defense;
  const vpLine = d?.valid_points?.[idx] ?? d?.valid_points?.[0];
  const q = span.quote?.trim();
  const parts = [
    q ? `“${q.length > 400 ? `${q.slice(0, 400)}…` : q}”` : '',
    vpLine,
    d?.defense?.trim(),
  ].filter(Boolean);
  return { title: `Advocate · evidence ${idx + 1}`, body: parts.join('\n\n') || '—' };
}

function bubbleForJudgment(g: GraphChunkJudgment, idx: number, span: EvidenceSpanPayload): { title: string; body: string } {
  const diagnosis = firstSentence(g.core_issue) || firstSentence(g.guidance) || firstSentence(g.reasoning);
  return {
    title: `Judgment · evidence ${idx + 1}`,
    body: diagnosis || '—',
  };
}

/** Full per-span critic + advocate synthesis for inline hover (not first-sentence truncated). */
function bubbleBodyForSynthesisSpan(span: SpanSynthesisPayload): string {
  const qRaw = span.quote?.trim();
  const q =
    qRaw && qRaw.length > 1200 ? `${qRaw.slice(0, 1200).trimEnd()}…` : qRaw;
  const c = (span.critic_blurb ?? '').trim();
  const a = (span.advocate_blurb ?? '').trim();
  const parts: string[] = [];
  if (q) parts.push(`“${q}”`);
  if (c) parts.push(`Critic\n${c}`);
  if (a) parts.push(`Advocate\n${a}`);
  return parts.join('\n\n') || '—';
}

/**
 * Build highlight ranges for one section row from graph advice and manuscript chunk span.
 */
export function buildEditorHighlightsForSection(
  sectionContent: string,
  chapter: ChapterDoc,
  sectionRowIndex: number,
  chunkSpan: ClientChunkSpan,
  graph: GraphChunkJudgment | null | undefined,
): { highlights: EditorEvidenceHighlight[]; anyStale: boolean } {
  const highlights: EditorEvidenceHighlight[] = [];
  if (!graph || !sectionContent) {
    return { highlights, anyStale: false };
  }

  const headerCp = sectionRowIndex === 0 ? chapterHeaderCp(chapter) : 0;
  const contentCpLen = countCodePoints(sectionContent);
  const c0 = chunkSpan.start_char;
  const c1 = chunkSpan.end_char;

  let anyStale = false;

  const pushSpans = (
    spans: EvidenceSpanPayload[] | undefined,
    source: EvidenceSource,
    bubbleFn: (idx: number, span: EvidenceSpanPayload) => { title: string; body: string },
  ) => {
    if (!spans?.length) return;
    spans.forEach((span, idx) => {
      const ov = spanOverlapsChunk(span, c0, c1);
      if (!ov) return;
      const ed = toEditorRange(ov, c0, headerCp, contentCpLen);
      if (!ed) return;
      if (quoteLooksStale(sectionContent, ed.startCp, ed.endCp, span.quote ?? '')) {
        anyStale = true;
      }
      const { title, body } = bubbleFn(idx, span);
      highlights.push({
        key: `${source}-${idx}`,
        source,
        startCp: ed.startCp,
        endCp: ed.endCp,
        quote: span.quote ?? '',
        normAnchor: normAnchorAtCp(sectionContent, ed.startCp),
        bubbleTitle: title,
        bubbleBody: body,
      });
    });
  };

  // If synthesis spans exist, use them. They map directly to the text and have synthesized blurbs.
  if (graph.synthesis_spans && graph.synthesis_spans.length > 0) {
    graph.synthesis_spans.forEach((span, idx) => {
      const ov = spanOverlapsChunk(span, c0, c1);
      if (!ov) return;
      const ed = toEditorRange(ov, c0, headerCp, contentCpLen);
      if (!ed) return;
      if (quoteLooksStale(sectionContent, ed.startCp, ed.endCp, span.quote ?? '')) {
        anyStale = true;
        // Synthesis spans are optional; skip stale mappings and fall back.
        return;
      }
      highlights.push({
        key: `synthesis-${idx}`,
        source: 'judgment',
        startCp: ed.startCp,
        endCp: ed.endCp,
        quote: span.quote ?? '',
        normAnchor: normAnchorAtCp(sectionContent, ed.startCp),
        bubbleTitle: `Synthesis · point ${idx + 1}`,
        bubbleBody: bubbleBodyForSynthesisSpan(span),
      });
    });
  } else {
    // Keep manuscript highlights focused and readable: judgment-only anchors.
    pushSpans(graph.judgment_evidence_spans, 'judgment', (i, s) => bubbleForJudgment(graph, i, s));
  }

  if (
    highlights.length === 0 &&
    contentCpLen > 0 &&
    (graph.core_issue?.trim() || graph.guidance?.trim() || graph.reasoning?.trim())
  ) {
    const end = Math.min(contentCpLen, 180);
    const b = bubbleForJudgment(graph, 0, { start_char: c0, end_char: c0 + end, quote: '' });
    highlights.push({
      key: 'judgment-0',
      source: 'judgment',
      startCp: 0,
      endCp: end,
      quote: '',
      normAnchor: 0,
      bubbleTitle: b.title,
      bubbleBody: b.body,
    });
    anyStale = true;
  }

  return { highlights, anyStale };
}
