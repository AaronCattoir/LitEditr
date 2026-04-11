import { Extension } from '@tiptap/core';
import type { Node as PMNode } from '@tiptap/pm/model';
import { Plugin, PluginKey } from '@tiptap/pm/state';
import { Decoration, DecorationSet } from '@tiptap/pm/view';
import type { EditorEvidenceHighlight } from '../../lib/evidenceMapping';

export const evidenceHighlightPluginKey = new PluginKey<DecorationSet>('evidenceHighlight');

export const EVIDENCE_HIGHLIGHT_UPDATE = 'evidenceHighlightUpdate';

/** Same character class as `normAnchorAtCp` in evidenceMapping.ts */
const STRIP_CHAR = /[\s.,!?;:"'“”‘’()\[\]{}_*\-#]/;
const STRIP_ALL = /[\s.,!?;:"'“”‘’()\[\]{}_*\-#]/g;

/**
 * Flatten visible text in document order with `\n\n` between top-level blocks.
 * `utf16ToPm[i]` = ProseMirror position of plain[i] (UTF-16 code unit).
 */
function flattenDocumentToPlain(doc: PMNode): { plain: string; utf16ToPm: number[] } {
  const utf16ToPm: number[] = [];
  const parts: string[] = [];
  let basePos = 1;

  doc.forEach((block) => {
    if (parts.length > 0) {
      parts.push('\n\n');
      utf16ToPm.push(basePos);
      utf16ToPm.push(basePos);
    }
    block.descendants((node, pos) => {
      if (node.isText && node.text) {
        const t = node.text;
        const abs = basePos + pos;
        for (let i = 0; i < t.length; i++) {
          utf16ToPm.push(abs + i);
        }
        parts.push(t);
      }
    });
    basePos += block.nodeSize;
  });

  const plain = parts.join('');
  return { plain, utf16ToPm };
}

function normIndexAtUtf16(plain: string, utf16End: number): number {
  let n = 0;
  for (let i = 0; i < utf16End && i < plain.length; ) {
    const ch = plain[i];
    if (!STRIP_CHAR.test(ch)) n += 1;
    i += utf16UnitsAt(plain, i);
  }
  return n;
}

function utf16UnitsAt(s: string, i: number): number {
  const c = s.charCodeAt(i);
  return c >= 0xd800 && c <= 0xdbff && i + 1 < s.length ? 2 : 1;
}

function pmEndAfterUtf16Range(plain: string, utf16ToPm: number[], start: number, end: number): number | null {
  if (start < 0 || end > plain.length || end <= start || !utf16ToPm.length) return null;
  const last = end - 1;
  const adv = utf16UnitsAt(plain, last);
  return utf16ToPm[last] + adv;
}

function pickBestOccurrence(
  candidates: number[],
  plain: string,
  normAnchor: number,
): number {
  if (candidates.length === 0) return -1;
  if (candidates.length === 1) return candidates[0];
  let best = candidates[0];
  let bestD = Math.abs(normIndexAtUtf16(plain, candidates[0]) - normAnchor);
  for (let i = 1; i < candidates.length; i++) {
    const idx = candidates[i];
    const d = Math.abs(normIndexAtUtf16(plain, idx) - normAnchor);
    if (d < bestD) {
      bestD = d;
      best = idx;
    }
  }
  return best;
}

function findAllIndices(hay: string, needle: string): number[] {
  const out: number[] = [];
  if (!needle) return out;
  let pos = 0;
  while (pos <= hay.length) {
    const i = hay.indexOf(needle, pos);
    if (i < 0) break;
    out.push(i);
    pos = i + 1;
  }
  return out;
}

function docPosFromCodePointOffset(doc: PMNode, offsetCp: number): number | null {
  let accCp = 0;
  let found: number | null = null;
  doc.descendants((node, pos) => {
    if (found !== null) return false;
    if (!node.isText || !node.text) return;
    const text = node.text;
    const cps = [...text].length;
    if (accCp + cps > offsetCp) {
      const needCp = offsetCp - accCp;
      let cp = 0;
      let utf16 = 0;
      for (const ch of text) {
        if (cp === needCp) {
          found = pos + utf16;
          return false;
        }
        cp += 1;
        utf16 += ch.length;
      }
      found = pos + text.length;
      return false;
    }
    accCp += cps;
  });
  return found;
}

function sourceClass(source: EditorEvidenceHighlight['source']): string {
  if (source === 'critic') return 'editr-evidence-critic';
  if (source === 'defense') return 'editr-evidence-defense';
  return 'editr-evidence-judgment';
}

function resolveHighlightRange(doc: PMNode, h: EditorEvidenceHighlight, flat: { plain: string; utf16ToPm: number[] }): { from: number; to: number } | null {
  const { plain, utf16ToPm } = flat;
  if (plain.length !== utf16ToPm.length) return null;

  const q = (h.quote ?? '').trim();
  const normAnchor = h.normAnchor ?? 0;

  // 1) Exact substring in flattened plain (handles **markdown** vs visible text if quote is plain)
  if (q.length >= 2) {
    const exact = findAllIndices(plain, q);
    if (exact.length) {
      const start = pickBestOccurrence(exact, plain, normAnchor);
      const end = start + q.length;
      const from = utf16ToPm[start];
      const to = pmEndAfterUtf16Range(plain, utf16ToPm, start, end);
      if (from !== undefined && to !== null && to > from) return { from, to };
    }
    const low = plain.toLowerCase();
    const qlow = q.toLowerCase();
    if (qlow !== q) {
      const hits: number[] = [];
      let pos = 0;
      while (pos <= low.length) {
        const i = low.indexOf(qlow, pos);
        if (i < 0) break;
        hits.push(i);
        pos = i + 1;
      }
      if (hits.length) {
        const start = pickBestOccurrence(hits, plain, normAnchor);
        const end = start + q.length;
        const from = utf16ToPm[start];
        const to = pmEndAfterUtf16Range(plain, utf16ToPm, start, end);
        if (from !== undefined && to !== null && to > from) return { from, to };
      }
    }
  }

  // 2) Normalized match (strip punctuation/whitespace) + tie-break with normAnchor (same space as evidenceMapping)
  const normQuote = q.replace(STRIP_ALL, '').toLowerCase();
  if (normQuote.length >= 4) {
    let normDoc = '';
    const posMap: number[] = [];
    for (let i = 0; i < plain.length; ) {
      const ch = plain[i];
      const adv = utf16UnitsAt(plain, i);
      if (!STRIP_CHAR.test(ch)) {
        normDoc += ch.toLowerCase();
        posMap.push(i);
      }
      i += adv;
    }
    const candidates: number[] = [];
    let search = 0;
    while (search <= normDoc.length) {
      const idx = normDoc.indexOf(normQuote, search);
      if (idx < 0) break;
      candidates.push(idx);
      search = idx + 1;
    }
    if (candidates.length) {
      // Indices are in normDoc space — same as normAnchor from evidenceMapping.
      let bestIdx = candidates[0];
      let bestD = Math.abs(candidates[0] - normAnchor);
      for (let j = 1; j < candidates.length; j++) {
        const idx = candidates[j];
        const d = Math.abs(idx - normAnchor);
        if (d < bestD) {
          bestD = d;
          bestIdx = idx;
        }
      }
      const startUtf = posMap[bestIdx];
      const endUtf = posMap[bestIdx + normQuote.length - 1];
      if (startUtf === undefined || endUtf === undefined) return null;
      const from = utf16ToPm[startUtf];
      const endExclusive = endUtf + utf16UnitsAt(plain, endUtf);
      const to = pmEndAfterUtf16Range(plain, utf16ToPm, startUtf, endExclusive);
      if (from !== undefined && to !== null && to > from) return { from, to };
    }
  }

  // 3) Legacy: code-point offsets in section markdown (often wrong vs PM, last resort)
  const from = docPosFromCodePointOffset(doc, h.startCp);
  const to = docPosFromCodePointOffset(doc, h.endCp);
  if (from !== null && to !== null && to > from) return { from, to };
  return null;
}

function buildDecorationSet(doc: PMNode, highlights: EditorEvidenceHighlight[]): DecorationSet {
  const flat = flattenDocumentToPlain(doc);
  const decos: Decoration[] = [];
  for (const h of highlights) {
    const range = resolveHighlightRange(doc, h, flat);
    if (!range) continue;
    decos.push(
      Decoration.inline(range.from, range.to, {
        class: `editr-evidence-highlight ${sourceClass(h.source)}`,
        'data-evidence-key': h.key,
        'data-evidence-source': h.source,
      }),
    );
  }
  return DecorationSet.create(doc, decos);
}

export const EvidenceHighlight = Extension.create({
  name: 'evidenceHighlight',

  addProseMirrorPlugins() {
    return [
      new Plugin({
        key: evidenceHighlightPluginKey,
        state: {
          init: (_, { doc }) => DecorationSet.empty,
          apply(tr, old, _oldState, newState) {
            const next = tr.getMeta(EVIDENCE_HIGHLIGHT_UPDATE) as EditorEvidenceHighlight[] | undefined;
            if (next !== undefined) {
              return buildDecorationSet(newState.doc, next);
            }
            if (tr.docChanged) {
              return old.map(tr.mapping, newState.doc);
            }
            return old;
          },
        },
        props: {
          decorations(state) {
            return evidenceHighlightPluginKey.getState(state) ?? DecorationSet.empty;
          },
        },
      }),
    ];
  },
});
