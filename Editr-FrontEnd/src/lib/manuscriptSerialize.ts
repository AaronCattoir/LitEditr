/**
 * Concatenate chapters + chunk rows into canonical manuscript text and client chunk spans
 * for POST /v1/revisions/{id}/analyze.
 *
 * Spans use **Unicode code point** indices (Python 3 `str` / PEP 393 semantics), not JS
 * `String.length` (UTF-16 code units). Otherwise emoji / supplementary characters shift
 * indices and the backend returns 422 “chunk spans must cover text contiguously”.
 */

import type { ChapterDoc, ClientChunkSpan, SectionData } from './api';

export function escapeChapterTitle(s: string): string {
  return s.replace(/\\/g, '\\\\').replace(/"/g, '\\"');
}

export function unescapeChapterTitle(s: string): string {
  return s.replace(/\\"/g, '"').replace(/\\\\/g, '\\');
}

export function buildChapterDelimiterLine(chapterId: string, title: string): string {
  return `<<<EDITR_CHAPTER id="${chapterId}" title="${escapeChapterTitle(title)}">>>\n`;
}

export interface ManuscriptBuildResult {
  documentText: string;
  chunks: ClientChunkSpan[];
}

const DEFAULT_SCENE_MARKER = '~';

/**
 * Marker-based section splitting is the default and is deterministic across save/reload.
 * Blank-line auto splitting is opt-in for legacy behavior.
 */
export function getSceneSplitMarker(): string {
  const raw = (import.meta.env.VITE_SCENE_SPLIT_MARKER ?? '').trim();
  return raw || DEFAULT_SCENE_MARKER;
}

export function autoSplitBlankLinesEnabled(): boolean {
  return String(import.meta.env.VITE_AUTO_SPLIT_BLANK_LINES ?? 'false').toLowerCase() === 'true';
}

export function buildSceneSeparatorLine(marker = getSceneSplitMarker()): string {
  return `\n${marker}\n`;
}

/** Unicode code point count — matches Python 3 `len(str)` for indexing chunk spans. */
export function countCodePoints(s: string): number {
  let n = 0;
  for (const _ of s) n++;
  return n;
}

/** Slice by Unicode code points — matches Python `text[start:end]` on `str`. */
export function sliceByCodePoints(s: string, start: number, end: number): string {
  return [...s].slice(start, end).join('');
}

/** Exact manuscript substring for a section id (same as analyze chunk spans). */
export function getManuscriptChunkText(chapters: ChapterDoc[], chunkId: string): string | null {
  const { documentText, chunks } = buildManuscriptAndChunks(chapters);
  const span = chunks.find((c) => c.chunk_id === chunkId);
  if (!span) return null;
  return sliceByCodePoints(documentText, span.start_char, span.end_char);
}

/** Chapters ordered by sortOrder then id. */
export function buildManuscriptAndChunks(chapters: ChapterDoc[]): ManuscriptBuildResult {
  const sorted = [...chapters].sort((a, b) => a.sortOrder - b.sortOrder || a.id.localeCompare(b.id));
  let doc = '';
  let cp = 0;
  const chunks: ClientChunkSpan[] = [];

  for (const ch of sorted) {
    const header = buildChapterDelimiterLine(ch.id, ch.title);
    const rows = ch.rows.length
      ? ch.rows
      : [
          {
            id: crypto.randomUUID(),
            content: '',
            isEditing: false,
            status: 'draft' as const,
          },
        ];

    for (let i = 0; i < rows.length; i++) {
      const row = rows[i];
      const start = cp;
      const piece = i === 0 ? header + row.content : row.content;
      doc += piece;
      cp += countCodePoints(piece);
      if (i < rows.length - 1) {
        // Include the inter-section separator inside this chunk's span so
        // the full document text is contiguously covered with no gap between chunks.
        const sep = buildSceneSeparatorLine();
        doc += sep;
        cp += countCodePoints(sep);
      }
      chunks.push({ chunk_id: row.id, start_char: start, end_char: cp });
    }
  }

  return { documentText: doc, chunks };
}

/**
 * Scene breaks are lines that contain only the configured marker (default `~`),
 * not inline occurrences (e.g. `a ~ b`).
 * Used for paste, manual split, and plain-text import.
 *
 * Segments are **not** `.trim()`'d: trimming removed leading/trailing newlines and spaces
 * that matter for Markdown paragraphs (and for Word/docx plain-text paste fidelity).
 * Empty segments (only whitespace) are skipped.
 */
export function splitOnSceneMarkers(text: string, marker = getSceneSplitMarker()): string[] {
  const m = marker.trim() || DEFAULT_SCENE_MARKER;
  const normalized = text.replace(/\r\n/g, '\n').replace(/\r/g, '\n');
  const lines = normalized.split('\n');
  const parts: string[] = [];
  let buf: string[] = [];
  const pushBuf = () => {
    if (!buf.length) return;
    const segment = buf.join('\n');
    if (segment.replace(/\s/g, '').length > 0) parts.push(segment);
    buf = [];
  };
  for (const line of lines) {
    if (line.trim() === m) {
      pushBuf();
    } else {
      buf.push(line);
    }
  }
  pushBuf();
  return parts;
}

export function validateManuscriptBuild(
  built: ManuscriptBuildResult,
): { ok: true } | { ok: false; message: string } {
  const { documentText, chunks } = built;
  const total = countCodePoints(documentText);
  if (chunks.length === 0) {
    return { ok: false, message: 'No sections to analyze. Add at least one section.' };
  }
  const sorted = [...chunks].sort((a, b) => a.start_char - b.start_char);
  if (sorted[0].start_char !== 0) {
    return {
      ok: false,
      message: `Manuscript build error: first chunk must start at 0 (got ${sorted[0].start_char}).`,
    };
  }
  for (let i = 0; i < sorted.length; i++) {
    const c = sorted[i];
    if (c.start_char >= c.end_char) {
      return { ok: false, message: `Invalid chunk span for ${c.chunk_id}: start must be less than end.` };
    }
    if (i > 0 && sorted[i - 1].end_char !== c.start_char) {
      return {
        ok: false,
        message: `Chunk spans are not contiguous: gap or overlap before chunk ${c.chunk_id}.`,
      };
    }
  }
  const last = sorted[sorted.length - 1];
  if (last.end_char !== total) {
    return {
      ok: false,
      message: `Chunk spans do not cover the full manuscript (expected end ${total}, got ${last.end_char}).`,
    };
  }
  return { ok: true };
}

const DELIM_RE = /<<<EDITR_CHAPTER id="([^"]+)" title="((?:[^"\\]|\\.)*)">>>\n/g;

/** Best-effort inverse of buildManuscriptAndChunks for bookmark restore / server text. */
export function parseManuscriptToChapters(text: string): ChapterDoc[] {
  const matches = [...text.matchAll(DELIM_RE)];
  if (matches.length === 0) {
    return [
      {
        id: crypto.randomUUID(),
        title: 'Chapter 1',
        sortOrder: 0,
        rows: [emptySection(text)],
      },
    ];
  }

  const out: ChapterDoc[] = [];
  for (let i = 0; i < matches.length; i++) {
    const m = matches[i];
    const start = m.index! + m[0].length;
    const end = i + 1 < matches.length ? matches[i + 1].index! : text.length;
    let body = text.slice(start, end);
    if (i === 0 && matches.length === 1 && !body.trim()) {
      body = '';
    }
    let parts = splitOnSceneMarkers(body);
    if (parts.length <= 1 && autoSplitBlankLinesEnabled()) {
      parts = body.split(/\n\n+/);
    }
    const rows: SectionData[] =
      parts.length && parts.some((p) => p.trim())
        ? parts.map((content) => ({
            id: crypto.randomUUID(),
            content,
            isEditing: false,
            status: 'draft',
          }))
        : [emptySection('')];
    out.push({
      id: m[1],
      title: unescapeChapterTitle(m[2]),
      sortOrder: i,
      rows,
    });
  }
  return out;
}

function emptySection(content: string): SectionData {
  return {
    id: crypto.randomUUID(),
    content,
    isEditing: false,
    status: 'draft',
  };
}
