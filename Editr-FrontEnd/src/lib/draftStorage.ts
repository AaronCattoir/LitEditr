import type { ChapterDoc, ProjectMetadata } from './api';

export const DRAFT_VERSION = 1 as const;

/**
 * Section `submitting` is an in-memory request flag. It must never survive hydration:
 * a timed-out quick coach + debounced save can persist it to localStorage and strand the UI.
 */
export function clearTransientSectionStatuses(chapters: ChapterDoc[]): ChapterDoc[] {
  return chapters.map((ch) => ({
    ...ch,
    rows: ch.rows.map((r) => (r.status === 'submitting' ? { ...r, status: 'draft' as const } : r)),
  }));
}

export const PENDING_DRAFT_KEY = 'editr:draft:pending';

export interface DraftPayload {
  version: typeof DRAFT_VERSION;
  chapters: ChapterDoc[];
  activeChapterId: string;
  metadata: ProjectMetadata;
}

export interface PendingDraftPayload extends DraftPayload {
  savedAt: string;
}

export function draftStorageKey(documentId: string): string {
  return `editr:draft:${documentId}`;
}

export function loadDraft(documentId: string): DraftPayload | null {
  try {
    const raw = localStorage.getItem(draftStorageKey(documentId));
    if (!raw) return null;
    const data = JSON.parse(raw) as DraftPayload;
    if (data.version !== DRAFT_VERSION || !Array.isArray(data.chapters)) return null;
    return data;
  } catch {
    return null;
  }
}

export function saveDraft(documentId: string, payload: DraftPayload): void {
  try {
    localStorage.setItem(draftStorageKey(documentId), JSON.stringify(payload));
  } catch {
    /* quota / private mode */
  }
}

export function clearDraft(documentId: string): void {
  try {
    localStorage.removeItem(draftStorageKey(documentId));
  } catch {
    /* ignore */
  }
}

export function loadPendingDraft(): PendingDraftPayload | null {
  try {
    const raw = localStorage.getItem(PENDING_DRAFT_KEY);
    if (!raw) return null;
    const data = JSON.parse(raw) as PendingDraftPayload;
    if (data.version !== DRAFT_VERSION || !Array.isArray(data.chapters)) return null;
    if (typeof data.savedAt !== 'string') return null;
    return data;
  } catch {
    return null;
  }
}

export function savePendingDraft(payload: DraftPayload): void {
  try {
    const withTime: PendingDraftPayload = {
      ...payload,
      savedAt: new Date().toISOString(),
    };
    localStorage.setItem(PENDING_DRAFT_KEY, JSON.stringify(withTime));
  } catch {
    /* quota / private mode */
  }
}

export function clearPendingDraft(): void {
  try {
    localStorage.removeItem(PENDING_DRAFT_KEY);
  } catch {
    /* ignore */
  }
}
