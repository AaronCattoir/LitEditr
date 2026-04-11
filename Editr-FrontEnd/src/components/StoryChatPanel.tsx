import React, { useCallback, useEffect, useRef, useState } from 'react';
import { motion } from 'motion/react';
import { X, Loader2, Send } from 'lucide-react';
import {
  postStoryChat,
  postStoryChatSessionClose,
  listStoryChatTurns,
  type BetaLlmProviderId,
  type InkblotVisualState,
} from '../lib/api';
import { InkblotAvatar } from './InkblotAvatar';
import {
  STORY_CHAT_STORAGE_VERSION,
  INKBLOT_STARTER_USER_MESSAGE,
  QUICK_COACH_STORY_CHAT_USER_MESSAGE,
  loadStoryChatStored,
  saveStoryChatStored,
  clearStoryChatStored,
} from '../lib/storyChatStorage';
import { cn } from '../lib/utils';

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
}

function mapTurnsToMessages(turns: Record<string, unknown>[]): ChatMessage[] {
  const out: ChatMessage[] = [];
  for (const t of turns) {
    const role = String(t.role ?? '');
    const content = String(t.content ?? '');
    if (role === 'user' && content === INKBLOT_STARTER_USER_MESSAGE) continue;
    /* Synthetic sparkle handoff — hide so chat does not look like a second user line / “stuck in QC”. */
    if (role === 'user' && content === QUICK_COACH_STORY_CHAT_USER_MESSAGE) continue;
    if (role !== 'user' && role !== 'assistant') continue;
    const idx = t.turn_index;
    out.push({
      id: `turn-${typeof idx === 'number' ? idx : out.length}`,
      role,
      content,
    });
  }
  return out;
}

interface StoryChatPanelProps {
  isOpen: boolean;
  onClose: () => void;
  documentId: string;
  revisionId?: string | null;
  /** Current chapter id for explicit context (chapter slice / first 5k words). */
  chapterId: string;
  chunkOptions: Array<{ id: string; label: string }>;
  provider: BetaLlmProviderId | null;
  assertProviderReady: () => boolean;
  inkblotVisual: InkblotVisualState | null;
  /** Increment (e.g. after quick coach) to refetch turns while panel is open. */
  turnsRefreshSignal?: number;
}

export function StoryChatPanel({
  isOpen,
  onClose,
  documentId,
  revisionId,
  chapterId,
  chunkOptions,
  provider,
  assertProviderReady,
  inkblotVisual,
  turnsRefreshSignal = 0,
}: StoryChatPanelProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [hydrating, setHydrating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedChunkIds, setSelectedChunkIds] = useState<string[]>([]);
  const listRef = useRef<HTMLDivElement>(null);
  const lastDocIdRef = useRef<string | null>(null);
  const prevIsOpenRef = useRef(isOpen);
  const messagesRef = useRef<ChatMessage[]>([]);
  messagesRef.current = messages;

  /** When the panel closes, enqueue server-side full-session memory extraction. */
  useEffect(() => {
    const wasOpen = prevIsOpenRef.current;
    prevIsOpenRef.current = isOpen;
    if (wasOpen && !isOpen && sessionId && documentId) {
      void postStoryChatSessionClose(documentId, sessionId, { provider: provider ?? undefined }).catch(() => {
        /* offline / tab close — best effort */
      });
    }
  }, [isOpen, sessionId, documentId, provider]);

  useEffect(() => {
    if (documentId !== lastDocIdRef.current) {
      lastDocIdRef.current = documentId;
      setMessages([]);
      setSessionId(null);
      setError(null);
      setSelectedChunkIds([]);
    }
  }, [documentId]);

  useEffect(() => {
    const valid = new Set(chunkOptions.map((c) => c.id));
    setSelectedChunkIds((prev) => prev.filter((id) => valid.has(id)));
  }, [chunkOptions]);

  const scrollToBottom = useCallback(() => {
    const el = listRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  const hydrateOrBootstrap = useCallback(
    async (signal?: AbortSignal) => {
      if (!documentId) return;
      setError(null);
      setHydrating(true);
      try {
        const validIds = new Set(chunkOptions.map((c) => c.id));
        const stored = loadStoryChatStored(documentId);
        const pinned = (stored?.pinned_chunk_ids ?? []).filter((id) => validIds.has(id));
        const scopeChunkIds = pinned.length > 0 ? pinned : selectedChunkIds;

        let sid = stored?.session_id ?? null;

        if (sid) {
          try {
            const { turns } = await listStoryChatTurns(sid);
            if (signal?.aborted) return;
            const mapped = mapTurnsToMessages(turns);
            if (mapped.length > 0) {
              setSessionId(sid);
              setMessages(mapped);
              if (pinned.length > 0) {
                setSelectedChunkIds(pinned);
                saveStoryChatStored(documentId, {
                  version: STORY_CHAT_STORAGE_VERSION,
                  session_id: sid,
                });
              }
              return;
            }
          } catch {
            clearStoryChatStored(documentId);
            sid = null;
          }
        }

        if (signal?.aborted) return;
        if (!assertProviderReady()) return;

        const resp = await postStoryChat(documentId, {
          user_message: INKBLOT_STARTER_USER_MESSAGE,
          session_id: null,
          revision_id: revisionId ?? undefined,
          chunk_ids: scopeChunkIds.length > 0 ? scopeChunkIds : undefined,
          chapter_id: scopeChunkIds.length > 0 ? undefined : chapterId,
          provider: provider ?? undefined,
        });
        if (signal?.aborted) return;
        setSessionId(resp.session_id);
        if (pinned.length > 0) {
          setSelectedChunkIds(pinned);
        }
        saveStoryChatStored(documentId, {
          version: STORY_CHAT_STORAGE_VERSION,
          session_id: resp.session_id,
        });
        setMessages([{ id: 'greeting', role: 'assistant', content: resp.answer }]);
      } catch (e) {
        if (signal?.aborted) return;
        const msg = e instanceof Error ? e.message : 'Could not start Inkblot chat.';
        setError(msg);
      } finally {
        setHydrating(false);
      }
    },
    [documentId, revisionId, chapterId, selectedChunkIds, chunkOptions, provider, assertProviderReady],
  );

  useEffect(() => {
    if (!isOpen || !documentId) return;
    if (messagesRef.current.length > 0) return;
    const ac = new AbortController();
    void hydrateOrBootstrap(ac.signal);
    return () => ac.abort();
  }, [isOpen, documentId, hydrateOrBootstrap]);

  useEffect(() => {
    if (!isOpen || !documentId || turnsRefreshSignal <= 0) return;
    const stored = loadStoryChatStored(documentId);
    const sid = stored?.session_id;
    if (!sid) return;
    const validIds = new Set(chunkOptions.map((c) => c.id));
    const pinned = (stored?.pinned_chunk_ids ?? []).filter((id) => validIds.has(id));
    let cancelled = false;
    void (async () => {
      try {
        const { turns } = await listStoryChatTurns(sid);
        if (cancelled) return;
        setSessionId(sid);
        setMessages(mapTurnsToMessages(turns));
        if (pinned.length > 0) {
          setSelectedChunkIds(pinned);
          saveStoryChatStored(documentId, {
            version: STORY_CHAT_STORAGE_VERSION,
            session_id: sid,
          });
        }
      } catch {
        /* ignore */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [turnsRefreshSignal, isOpen, documentId, chunkOptions]);

  const handleSend = async () => {
    const text = input.trim();
    if (!text || loading || hydrating) return;
    if (!assertProviderReady()) return;

    setLoading(true);
    setError(null);
    setInput('');
    const userMsg: ChatMessage = { id: `u-${Date.now()}`, role: 'user', content: text };
    setMessages((m) => [...m, userMsg]);

    try {
      const resp = await postStoryChat(documentId, {
        user_message: text,
        session_id: sessionId,
        revision_id: revisionId ?? undefined,
        chunk_ids: selectedChunkIds.length > 0 ? selectedChunkIds : undefined,
        chapter_id: selectedChunkIds.length > 0 ? undefined : chapterId,
        provider: provider ?? undefined,
      });
      setSessionId(resp.session_id);
      saveStoryChatStored(documentId, {
        version: STORY_CHAT_STORAGE_VERSION,
        session_id: resp.session_id,
      });
      setMessages((m) => [
        ...m,
        { id: `a-${Date.now()}`, role: 'assistant', content: resp.answer },
      ]);
    } catch (e) {
      setMessages((m) => m.filter((x) => x.id !== userMsg.id));
      setInput(text);
      setError(e instanceof Error ? e.message : 'Send failed.');
    } finally {
      setLoading(false);
    }
  };

  const busy = loading || hydrating;
  const handleResetChat = async () => {
    if (busy) return;
    clearStoryChatStored(documentId);
    setSessionId(null);
    setMessages([]);
    setInput('');
    setError(null);
    await hydrateOrBootstrap();
  };

  return (
    <motion.div
      initial={{ x: '-100%', opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      exit={{ x: '-100%', opacity: 0 }}
      transition={{ type: 'spring', damping: 28, stiffness: 220 }}
      className={cn(
        'fixed left-0 top-0 bottom-0 w-[calc(20rem+10vw)] max-w-[min(32rem,95vw)]',
        'bg-surface border-r border-border shadow-2xl z-30 overflow-hidden font-sans flex flex-col',
      )}
      aria-hidden={!isOpen}
    >
      <div className="shrink-0 flex items-center justify-between gap-2 px-4 py-3 border-b border-border bg-paper/80 backdrop-blur-sm">
        <div className="flex items-center gap-2 min-w-0">
          <InkblotAvatar
            visual={inkblotVisual}
            size={36}
            status={busy ? 'thinking' : 'idle'}
            className="text-accent"
          />
          <div className="min-w-0">
            <h2 className="text-sm font-semibold text-ink truncate">Inkblot</h2>
            <p className="text-xs text-ink-light truncate">Story chat</p>
          </div>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <button
            type="button"
            onClick={() => void handleResetChat()}
            disabled={busy}
            className="px-2 py-1 text-xs rounded-md border border-border text-ink-light hover:text-ink hover:bg-overlay disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            title="Reset chat"
          >
            Reset
          </button>
          <button
            type="button"
            onClick={onClose}
            className="p-2 rounded-full hover:bg-overlay text-ink-light hover:text-ink transition-colors"
            title="Close"
          >
            <X size={18} />
          </button>
        </div>
      </div>
      <div className="shrink-0 border-b border-border px-4 py-2 bg-paper/60">
        <div className="flex items-center justify-between gap-2">
          <p className="text-xs text-ink-light">
            Context: {selectedChunkIds.length > 0 ? `${selectedChunkIds.length} selected section(s)` : 'Active chapter (first 5k words)'}
          </p>
          {selectedChunkIds.length > 0 && (
            <button
              type="button"
              className="text-xs underline text-ink-light hover:text-ink"
              onClick={() => setSelectedChunkIds([])}
            >
              Clear
            </button>
          )}
        </div>
        {chunkOptions.length > 0 && (
          <details className="mt-1">
            <summary className="cursor-pointer text-xs text-ink hover:text-accent select-none">
              Choose sections
            </summary>
            <div className="mt-2 max-h-28 overflow-y-auto space-y-1 pr-1">
              {chunkOptions.map((opt) => {
                const checked = selectedChunkIds.includes(opt.id);
                return (
                  <label key={opt.id} className="flex items-start gap-2 text-xs text-ink-light">
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={(e) => {
                        const on = e.target.checked;
                        setSelectedChunkIds((prev) =>
                          on ? [...prev, opt.id] : prev.filter((id) => id !== opt.id),
                        );
                      }}
                      className="mt-0.5"
                    />
                    <span className="leading-snug">{opt.label}</span>
                  </label>
                );
              })}
            </div>
          </details>
        )}
      </div>

      <div
        ref={listRef}
        className="flex-1 overflow-y-auto px-4 py-3 space-y-3 text-sm"
      >
        {hydrating && messages.length === 0 && (
          <div className="flex items-center gap-2 text-ink-light">
            <Loader2 size={16} className="animate-spin shrink-0" />
            <span>Starting chat…</span>
          </div>
        )}
        {messages.map((m) => (
          <div
            key={m.id}
            className={cn(
              'rounded-lg px-3 py-2 max-w-[95%] whitespace-pre-wrap break-words',
              m.role === 'user'
                ? 'ml-auto bg-accent/15 text-ink border border-accent/30'
                : 'mr-auto bg-overlay/80 text-ink-light border border-border/60',
            )}
          >
            {m.content}
          </div>
        ))}
        {loading && (
          <div className="flex items-center gap-2 text-ink-light text-xs">
            <Loader2 size={14} className="animate-spin" />
            Inkblot is thinking…
          </div>
        )}
      </div>

      {error && (
        <div className="shrink-0 px-4 py-2 text-xs text-red-600 dark:text-red-400 border-t border-border bg-paper/90">
          {error}
          <button
            type="button"
            className="ml-2 underline font-medium"
            onClick={() => {
              void hydrateOrBootstrap();
            }}
          >
            Retry
          </button>
        </div>
      )}

      <div className="shrink-0 p-3 border-t border-border bg-paper/80">
        <div className="flex gap-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                void handleSend();
              }
            }}
            placeholder="Ask Inkblot…"
            rows={2}
            disabled={busy}
            className="flex-1 resize-none rounded-lg border border-border bg-paper px-3 py-2 text-sm text-ink placeholder:text-ink-light/60 focus:outline-none focus:ring-2 focus:ring-accent/40 disabled:opacity-50"
          />
          <button
            type="button"
            onClick={() => void handleSend()}
            disabled={busy || !input.trim()}
            className="self-end shrink-0 p-3 rounded-lg bg-accent text-paper hover:bg-accent-hover disabled:opacity-40 transition-colors"
            title="Send"
          >
            {loading ? <Loader2 size={18} className="animate-spin" /> : <Send size={18} />}
          </button>
        </div>
      </div>
    </motion.div>
  );
}
