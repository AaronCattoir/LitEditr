/**
 * Per-document Inkblot story-chat session id in localStorage (browser persistence).
 */

export const STORY_CHAT_STORAGE_VERSION = 1 as const;

/** Sent as the first user turn so the backend generates a non-cold greeting; hidden in UI when replaying turns. */
export const INKBLOT_STARTER_USER_MESSAGE =
  '[Inkblot] Give a brief warm greeting (1–3 sentences) as Inkblot for this story. Sound like you belong in the manuscript’s voice. Say you’re ready to help with the passage in context—no bullet lists.';

/** Must match `QUICK_COACH_STORY_CHAT_USER_MESSAGE` in backend `quick_coach_story_chat.py` (synthetic turn when sparkle appends to chat). */
export const QUICK_COACH_STORY_CHAT_USER_MESSAGE = 'Quick coach for this section.';

export interface StoryChatStored {
  version: typeof STORY_CHAT_STORAGE_VERSION;
  session_id: string | null;
  /** After quick-coach → Inkblot handoff: narrow chat to these section ids until consumed. */
  pinned_chunk_ids?: string[];
}

export function storyChatStorageKey(documentId: string): string {
  return `editr:story-chat:${documentId}`;
}

export function loadStoryChatStored(documentId: string): StoryChatStored | null {
  try {
    const raw = localStorage.getItem(storyChatStorageKey(documentId));
    if (!raw) return null;
    const data = JSON.parse(raw) as StoryChatStored;
    if (data.version !== STORY_CHAT_STORAGE_VERSION) return null;
    if (data.session_id != null && typeof data.session_id !== 'string') return null;
    if (data.pinned_chunk_ids != null) {
      if (!Array.isArray(data.pinned_chunk_ids)) return null;
      if (!data.pinned_chunk_ids.every((x) => typeof x === 'string')) return null;
    }
    return data;
  } catch {
    return null;
  }
}

export function saveStoryChatStored(documentId: string, payload: StoryChatStored): void {
  try {
    localStorage.setItem(storyChatStorageKey(documentId), JSON.stringify(payload));
  } catch {
    /* quota / private mode */
  }
}

export function clearStoryChatStored(documentId: string): void {
  try {
    localStorage.removeItem(storyChatStorageKey(documentId));
  } catch {
    /* ignore */
  }
}
