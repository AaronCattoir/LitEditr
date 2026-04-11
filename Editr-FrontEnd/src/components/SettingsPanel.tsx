import React, { useEffect, useState, useMemo } from 'react';
import { motion } from 'motion/react';
import { X, BookOpen, Users, MapPin, Tag, Bookmark, Download, Cpu, Printer } from 'lucide-react';
import {
  ProjectMetadata,
  listDocumentBookmarks,
  createBookmark,
  restoreBookmark,
  type RestorePayload,
  type BookmarkRow,
  type RuntimeProvidersResponse,
  type BetaLlmProviderId,
} from '../lib/api';

interface SettingsPanelProps {
  metadata: ProjectMetadata;
  onUpdate: (metadata: ProjectMetadata) => void;
  onClose: () => void;
  isOpen: boolean;
  documentId?: string;
  revisionId?: string;
  runId?: string;
  useMockApi?: boolean;
  onRestore?: (payload: RestorePayload) => void;
  /** Download current manuscript text (chapters + sections, same format as save/analyze). */
  onExportStory?: () => void;
  /** Open browser print flow for current manuscript only (no notes/panels). */
  onPrintStory?: () => void;
  runtimeProviders?: RuntimeProvidersResponse | null;
  runtimeProvidersError?: string | null;
}

export function SettingsPanel({
  metadata,
  onUpdate,
  onClose,
  isOpen,
  documentId,
  revisionId,
  runId,
  useMockApi = false,
  onRestore,
  onExportStory,
  onPrintStory,
  runtimeProviders = null,
  runtimeProvidersError = null,
}: SettingsPanelProps) {
  const [bookmarks, setBookmarks] = useState<BookmarkRow[]>([]);
  const [bookmarkLabel, setBookmarkLabel] = useState('');
  const [bookmarkBusy, setBookmarkBusy] = useState(false);
  const hasSceneOrCast = useMemo(
    () => Boolean(metadata.scene.trim()) || metadata.characters.length > 0,
    [metadata.scene, metadata.characters],
  );
  const [showSceneCast, setShowSceneCast] = useState(hasSceneOrCast);
  useEffect(() => {
    if (hasSceneOrCast) setShowSceneCast(true);
  }, [hasSceneOrCast]);

  useEffect(() => {
    if (!documentId || useMockApi) {
      setBookmarks([]);
      return;
    }
    listDocumentBookmarks(documentId)
      .then((r) => setBookmarks(r.bookmarks))
      .catch(() => setBookmarks([]));
  }, [documentId, useMockApi]);

  if (!isOpen) return null;

  const handleChange = (field: keyof ProjectMetadata, value: string | string[] | boolean) => {
    onUpdate({
      ...metadata,
      [field]: value,
    });
  };

  const handleProviderPick = (id: BetaLlmProviderId) => {
    onUpdate({ ...metadata, llmProvider: id });
  };

  const providerLabel = (id: BetaLlmProviderId) => (id === 'openai' ? 'OpenAI' : 'Gemini');

  return (
    <motion.div
      initial={{ x: '100%', opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      exit={{ x: '100%', opacity: 0 }}
      transition={{ type: 'spring', damping: 25, stiffness: 200 }}
      className="fixed right-0 top-0 bottom-0 w-[calc(20rem+10vw)] max-w-[min(32rem,95vw)] bg-surface border-l border-border shadow-2xl z-20 overflow-y-auto font-sans flex flex-col"
    >
      <div className="sticky top-0 bg-surface/90 backdrop-blur-md border-b border-border px-6 py-4 flex items-center justify-between z-10">
        <h2 className="font-semibold text-ink text-lg">Project Settings</h2>
        <button 
          onClick={onClose}
          className="p-2 -mr-2 text-ink-light hover:text-ink hover:bg-overlay rounded-full transition-colors"
        >
          <X size={20} />
        </button>
      </div>

      <div className="p-6 flex flex-col gap-8 flex-1">
        <div className="flex flex-col gap-2">
          <label className="text-xs font-semibold uppercase tracking-wider text-ink-light flex items-center gap-2">
            <BookOpen size={14} />
            Title & Chapter
          </label>
          <input 
            type="text" 
            value={metadata.title}
            onChange={(e) => handleChange('title', e.target.value)}
            placeholder="Project Title"
            className="w-full px-3 py-2 rounded-lg bg-overlay border-transparent focus:bg-surface focus:border-accent focus:ring-2 focus:ring-accent/20 transition-all outline-none text-ink text-sm"
          />
          <input 
            type="text" 
            value={metadata.chapter}
            onChange={(e) => handleChange('chapter', e.target.value)}
            placeholder="Chapter Name"
            className="w-full px-3 py-2 rounded-lg bg-overlay border-transparent focus:bg-surface focus:border-accent focus:ring-2 focus:ring-accent/20 transition-all outline-none text-ink text-sm"
          />
        </div>

        <div className="flex flex-col gap-2">
          <label className="text-xs font-semibold uppercase tracking-wider text-ink-light flex items-center gap-2">
            <Tag size={14} />
            Genre
          </label>
          <input 
            type="text" 
            value={metadata.genre}
            onChange={(e) => handleChange('genre', e.target.value)}
            placeholder="e.g. Sci-Fi, Memoir"
            className="w-full px-3 py-2 rounded-lg bg-overlay border-transparent focus:bg-surface focus:border-accent focus:ring-2 focus:ring-accent/20 transition-all outline-none text-ink text-sm"
          />
          <label className="text-[11px] font-semibold uppercase tracking-wider text-ink-light mt-1">Subgenre tags</label>
          <input
            type="text"
            value={metadata.subgenreTags?.join(', ') ?? ''}
            onChange={(e) =>
              handleChange(
                'subgenreTags',
                e.target.value
                  .split(',')
                  .map((c) => c.trim())
                  .filter(Boolean),
              )
            }
            placeholder="Comma separated, optional"
            className="w-full px-3 py-2 rounded-lg bg-overlay border-transparent focus:bg-surface focus:border-accent focus:ring-2 focus:ring-accent/20 transition-all outline-none text-ink text-sm"
          />
          <label className="text-[11px] font-semibold uppercase tracking-wider text-ink-light mt-1">Tone descriptors</label>
          <input
            type="text"
            value={metadata.toneDescriptors?.join(', ') ?? ''}
            onChange={(e) =>
              handleChange(
                'toneDescriptors',
                e.target.value
                  .split(',')
                  .map((c) => c.trim())
                  .filter(Boolean),
              )
            }
            placeholder="Comma separated, optional"
            className="w-full px-3 py-2 rounded-lg bg-overlay border-transparent focus:bg-surface focus:border-accent focus:ring-2 focus:ring-accent/20 transition-all outline-none text-ink text-sm"
          />
          <label className="text-[11px] font-semibold uppercase tracking-wider text-ink-light mt-1">Reference authors</label>
          <input
            type="text"
            value={metadata.referenceAuthors?.join(', ') ?? ''}
            onChange={(e) =>
              handleChange(
                'referenceAuthors',
                e.target.value
                  .split(',')
                  .map((c) => c.trim())
                  .filter(Boolean),
              )
            }
            placeholder="Comma separated, optional"
            className="w-full px-3 py-2 rounded-lg bg-overlay border-transparent focus:bg-surface focus:border-accent focus:ring-2 focus:ring-accent/20 transition-all outline-none text-ink text-sm"
          />
        </div>

        {!useMockApi && (
          <div className="flex flex-col gap-3">
            <label className="text-xs font-semibold uppercase tracking-wider text-ink-light flex items-center gap-2">
              <Cpu size={14} />
              Model provider
            </label>
            {runtimeProvidersError ? (
              <p className="text-xs text-red-600 dark:text-red-400 leading-snug">{runtimeProvidersError}</p>
            ) : !runtimeProviders ? (
              <p className="text-xs text-ink-light/80">Loading provider status…</p>
            ) : (
              <div className="flex flex-col gap-2 rounded-lg border border-border/60 bg-overlay/50 p-3">
                <p className="text-xs text-ink-light/80 leading-snug">
                  API keys live on the server only (environment variables). This app never sees your keys.
                </p>
                <div className="flex flex-col gap-2.5">
                  {runtimeProviders.providers.map((p) => {
                    const selected = metadata.llmProvider === p.id;
                    return (
                      <label
                        key={p.id}
                        className={`flex items-start gap-3 cursor-pointer rounded-md px-2 py-1.5 -mx-2 transition-colors ${
                          p.configured ? 'hover:bg-overlay' : 'cursor-not-allowed opacity-60'
                        }`}
                      >
                        <input
                          type="radio"
                          name="editr-llm-provider"
                          className="mt-0.5 border-border text-accent focus:ring-accent/30"
                          checked={selected}
                          disabled={!p.configured}
                          onChange={() => handleProviderPick(p.id)}
                        />
                        <span className="text-sm text-ink leading-snug">
                          <span className="font-medium">{providerLabel(p.id)}</span>
                          <span className="block text-xs text-ink-light mt-0.5">
                            {p.configured ? (
                              <>Configured · default model {p.models.default}</>
                            ) : (
                              <>Not configured — set the matching key in the server environment</>
                            )}
                          </span>
                        </span>
                      </label>
                    );
                  })}
                </div>
                <p className="text-[11px] text-ink-light/60 leading-snug">
                  Typical variables: <code className="text-ink-light/80">OPENAI_API_KEY</code> for OpenAI;{' '}
                  <code className="text-ink-light/80">GEMINI_API_KEY</code> or{' '}
                  <code className="text-ink-light/80">GOOGLE_API_KEY</code> for Gemini.
                </p>
              </div>
            )}
          </div>
        )}

        <label className="flex items-start gap-3 cursor-pointer rounded-lg border border-border/60 bg-overlay/50 px-3 py-3">
          <input
            type="checkbox"
            className="mt-0.5 rounded border-border text-accent focus:ring-accent/30"
            checked={Boolean(metadata.shortStorySingleChapter)}
            onChange={(e) => handleChange('shortStorySingleChapter', e.target.checked)}
          />
          <span className="text-sm text-ink leading-snug">
            <span className="font-medium text-ink">Short story (single chapter)</span>
            <span className="block text-ink-light text-xs mt-1">
              Analysis and quick coach relax novel-style multi-chapter expectations; judge this piece on its own terms.
            </span>
          </span>
        </label>

        {showSceneCast ? (
          <>
            <div className="flex flex-col gap-2">
              <label className="text-xs font-semibold uppercase tracking-wider text-ink-light flex items-center gap-2">
                <MapPin size={14} />
                Scene &amp; setting (for analysis)
              </label>
              <p className="text-xs text-ink-light/80 leading-snug">
                Filled from story-wide analysis when you run Submit All; you can edit before the next run.
              </p>
              <textarea
                value={metadata.scene}
                onChange={(e) => handleChange('scene', e.target.value)}
                placeholder="Describe the setting…"
                rows={4}
                className="w-full px-3 py-2 rounded-lg bg-overlay border-transparent focus:bg-surface focus:border-accent focus:ring-2 focus:ring-accent/20 transition-all outline-none text-ink text-sm resize-none"
              />
            </div>

            <div className="flex flex-col gap-2">
              <label className="text-xs font-semibold uppercase tracking-wider text-ink-light flex items-center gap-2">
                <Users size={14} />
                Characters
              </label>
              <input
                type="text"
                value={metadata.characters.join(', ')}
                onChange={(e) =>
                  handleChange(
                    'characters',
                    e.target.value
                      .split(',')
                      .map((c) => c.trim())
                      .filter(Boolean),
                  )
                }
                placeholder="Comma separated…"
                className="w-full px-3 py-2 rounded-lg bg-overlay border-transparent focus:bg-surface focus:border-accent focus:ring-2 focus:ring-accent/20 transition-all outline-none text-ink text-sm"
              />
              {metadata.characters.length > 0 && (
                <div className="flex flex-wrap gap-2 mt-2">
                  {metadata.characters.map((char, i) => (
                    <span key={i} className="px-2.5 py-1 bg-accent/10 text-accent text-xs rounded-md font-medium">
                      {char}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </>
        ) : (
          <button
            type="button"
            onClick={() => setShowSceneCast(true)}
            className="text-left text-sm text-accent font-medium py-1 hover:underline"
          >
            + Add scene &amp; character hints (optional)
          </button>
        )}

        {metadata.plot && (
          <motion.div 
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className="flex flex-col gap-2 bg-accent/5 p-4 rounded-xl border border-accent/10"
          >
            <label className="text-xs font-semibold uppercase tracking-wider text-accent flex items-center gap-2">
              <BookOpen size={14} />
              Identified Plot
            </label>
            <p className="text-sm text-ink-light leading-relaxed">
              {metadata.plot}
            </p>
          </motion.div>
        )}

        {(onExportStory || onPrintStory) && (
          <div className="flex flex-col gap-2 border-t border-border pt-6">
            <label className="text-xs font-semibold uppercase tracking-wider text-ink-light flex items-center gap-2">
              <Download size={14} />
              Story manuscript
            </label>
            {onExportStory && (
              <button
                type="button"
                onClick={() => onExportStory()}
                className="w-full flex items-center justify-center gap-2 py-2.5 rounded-lg bg-overlay hover:bg-overlay/80 text-sm font-medium text-ink border border-border/60"
              >
                <Download size={16} />
                Download story (.md)
              </button>
            )}
            {onPrintStory && (
              <button
                type="button"
                onClick={() => onPrintStory()}
                className="w-full flex items-center justify-center gap-2 py-2.5 rounded-lg bg-overlay hover:bg-overlay/80 text-sm font-medium text-ink border border-border/60"
              >
                <Printer size={16} />
                Print story
              </button>
            )}
            <p className="text-xs text-ink-light/70 leading-relaxed">
              Exports Markdown (same as the rich editor: headings, lists, emphasis). Chapter delimiters and scene markers
              (~) are preserved for re-import. Print opens a story-only document and uses your browser print dialog.
            </p>
          </div>
        )}

        {!useMockApi && documentId && (
          <div className="flex flex-col gap-2 border-t border-border pt-6">
            <label className="text-xs font-semibold uppercase tracking-wider text-ink-light flex items-center gap-2">
              <Bookmark size={14} />
              Bookmarks
            </label>
            <div className="flex gap-2">
              <input
                type="text"
                value={bookmarkLabel}
                onChange={(e) => setBookmarkLabel(e.target.value)}
                placeholder="Label"
                className="flex-1 px-3 py-2 rounded-lg bg-overlay text-sm outline-none focus:ring-2 focus:ring-accent/20"
              />
              <button
                type="button"
                disabled={!revisionId || !bookmarkLabel.trim() || bookmarkBusy}
                onClick={async () => {
                  if (!documentId || !revisionId || !bookmarkLabel.trim()) return;
                  setBookmarkBusy(true);
                  try {
                    await createBookmark(documentId, {
                      label: bookmarkLabel.trim(),
                      revision_id: revisionId,
                      run_id: runId ?? null,
                    });
                    setBookmarkLabel('');
                    const r = await listDocumentBookmarks(documentId);
                    setBookmarks(r.bookmarks);
                  } catch (e) {
                    console.error(e);
                  } finally {
                    setBookmarkBusy(false);
                  }
                }}
                className="px-3 py-2 rounded-lg bg-ink text-paper text-sm disabled:opacity-50"
              >
                Save
              </button>
            </div>
            <ul className="space-y-2 max-h-40 overflow-y-auto">
              {bookmarks.map((b) => (
                <li key={b.id} className="flex items-center justify-between gap-2 text-sm">
                  <span className="truncate text-ink-light">{b.label}</span>
                  <button
                    type="button"
                    className="shrink-0 text-accent text-xs font-medium"
                    onClick={async () => {
                      try {
                        const payload = await restoreBookmark(b.id);
                        onRestore?.(payload);
                        onClose();
                      } catch (e) {
                        console.error(e);
                      }
                    }}
                  >
                    Restore
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
      
      <div className="p-6 border-t border-border bg-overlay">
        <p className="text-xs text-ink-light/60 leading-relaxed">
          This metadata is sent to your LangGraph coach to provide better, context-aware feedback on your writing.
        </p>
      </div>
    </motion.div>
  );
}
