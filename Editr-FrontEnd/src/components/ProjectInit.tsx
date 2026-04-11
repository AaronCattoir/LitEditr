import React, { useEffect, useState } from 'react';
import { motion } from 'motion/react';
import { Feather, Sparkles, Loader2, FolderOpen, Plus, Trash2 } from 'lucide-react';
import {
  type ProjectBootstrap,
  type ChapterDoc,
  type DocumentListRow,
  type EditorialReportPayload,
  buildJudgmentMap,
  useMockApi,
  createDocument,
  createDocumentChapter,
  getLatestRevisionAnalysis,
  listRevisionChunks,
  listDocuments,
  deleteDocument,
  getDocumentManuscript,
  makeSectionRow,
} from '../lib/api';
import { parseManuscriptToChapters } from '../lib/manuscriptSerialize';
import { loadPendingDraft, clearPendingDraft, clearDraft } from '../lib/draftStorage';
import { clearStoryChatStored } from '../lib/storyChatStorage';
import { mergeMetadataFromAnalysisReport } from '../lib/storyWideMetadata';

const DEFAULT_SECTION = `# The Art of Slowing Down

Sometimes the most productive thing we can do is absolutely nothing. In a world that constantly demands our attention, choosing to pause is an act of quiet rebellion.`;

interface ProjectInitProps {
  onBootstrap: (bootstrap: ProjectBootstrap) => void;
}

type Tab = 'new' | 'load';

export function ProjectInit({ onBootstrap }: ProjectInitProps) {
  const mock = useMockApi();
  const [tab, setTab] = useState<Tab>('new');
  const [pendingResume, setPendingResume] = useState<ReturnType<typeof loadPendingDraft>>(null);

  useEffect(() => {
    if (mock) setPendingResume(loadPendingDraft());
  }, [mock]);
  const [title, setTitle] = useState('');
  const [chapter, setChapter] = useState('Chapter 1');
  const [genre, setGenre] = useState('');
  const [subgenreTagsInput, setSubgenreTagsInput] = useState('');
  const [toneDescriptorsInput, setToneDescriptorsInput] = useState('');
  const [referenceAuthorsInput, setReferenceAuthorsInput] = useState('');
  const [scene, setScene] = useState('');
  const [characters, setCharacters] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Load tab
  const [docs, setDocs] = useState<DocumentListRow[]>([]);
  const [loadingDocs, setLoadingDocs] = useState(false);
  const [loadingDocId, setLoadingDocId] = useState<string | null>(null);
  const [deletingDocId, setDeletingDocId] = useState<string | null>(null);

  useEffect(() => {
    if (tab !== 'load' || mock) return;
    setLoadingDocs(true);
    listDocuments()
      .then((r) => setDocs(r.documents))
      .catch(() => setDocs([]))
      .finally(() => setLoadingDocs(false));
  }, [tab, mock]);

  const handleLoadDoc = async (doc: DocumentListRow) => {
    setLoadingDocId(doc.document_id);
    setError(null);
    try {
      const ms = await getDocumentManuscript(doc.document_id);
      let chapters = ms.current_revision
        ? parseManuscriptToChapters(ms.current_revision.full_text)
        : ms.chapters.length > 0
          ? ms.chapters.map((c, i) => ({
              id: c.chapter_id,
              title: c.title,
              sortOrder: c.sort_order,
              rows: [makeSectionRow('', false)],
            }))
          : [
              {
                id: crypto.randomUUID(),
                title: 'Chapter 1',
                sortOrder: 0,
                rows: [makeSectionRow('', false)],
              },
            ];
      let restoredRunId: string | undefined;
      let restoredSummary: string | undefined;
      let reportForMeta: EditorialReportPayload | null = null;
      if (ms.current_revision?.revision_id) {
        try {
          const chunkRes = await listRevisionChunks(ms.current_revision.revision_id);
          const sortedChunks = [...chunkRes.chunks].sort((a, b) => a.position - b.position);
          const flatRows = chapters.flatMap((c) => c.rows);
          if (sortedChunks.length === flatRows.length) {
            let idx = 0;
            chapters = chapters.map((ch) => ({
              ...ch,
              rows: ch.rows.map((r) => {
                const row = sortedChunks[idx++];
                return row ? { ...r, id: row.chunk_id } : r;
              }),
            }));
          }

          const latest = await getLatestRevisionAnalysis(ms.current_revision.revision_id);
          if (latest.report) {
            reportForMeta = latest.report;
            const map = buildJudgmentMap(latest.report);
            chapters = chapters.map((ch) => ({
              ...ch,
              rows: ch.rows.map((r) => {
                const g = map.get(r.id);
                return g ? { ...r, graphAdvice: g } : r;
              }),
            }));
            restoredRunId = latest.run_id ?? undefined;
            restoredSummary = latest.report.document_summary || undefined;
          }
        } catch {
          // Graceful fallback: load manuscript even if analysis hydration is unavailable.
        }
      }
      const meta = mergeMetadataFromAnalysisReport(
        {
          title: doc.title || 'Untitled',
          chapter: chapters[0]?.title ?? 'Chapter 1',
          genre: '',
          scene: '',
          characters: [],
          plot: restoredSummary,
          documentId: doc.document_id,
          revisionId: ms.current_revision?.revision_id,
          analyzedRevisionId: ms.current_revision?.revision_id,
          runId: restoredRunId,
        },
        reportForMeta,
      );
      onBootstrap({
        metadata: meta,
        chapters,
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not load document');
    } finally {
      setLoadingDocId(null);
    }
  };

  const handleDeleteDoc = async (doc: DocumentListRow, e: React.MouseEvent) => {
    e.stopPropagation();
    const label = doc.title?.trim() || 'Untitled';
    if (
      !window.confirm(
        `Delete “${label}” from this device? This removes the story and its saved analysis from the server. This cannot be undone.`,
      )
    ) {
      return;
    }
    setDeletingDocId(doc.document_id);
    setError(null);
    try {
      await deleteDocument(doc.document_id);
      clearDraft(doc.document_id);
      clearStoryChatStored(doc.document_id);
      setDocs((prev) => prev.filter((d) => d.document_id !== doc.document_id));
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Could not delete document';
      const notFound = message.includes('HTTP 404');
      if (notFound) {
        // Stale list entry or already-deleted document: remove card and clear local cache anyway.
        clearDraft(doc.document_id);
        clearStoryChatStored(doc.document_id);
        setDocs((prev) => prev.filter((d) => d.document_id !== doc.document_id));
        return;
      }
      setError(message);
    } finally {
      setDeletingDocId(null);
    }
  };

  const handleContinueDraft = () => {
    const p = loadPendingDraft();
    if (!p?.chapters?.length) {
      setPendingResume(null);
      return;
    }
    const idx = p.chapters.findIndex((c) => c.id === p.activeChapterId);
    const activeChapterId =
      idx >= 0 && p.chapters[idx] ? p.activeChapterId : p.chapters[0]?.id ?? '';
    onBootstrap({
      metadata: p.metadata,
      chapters: p.chapters,
      activeChapterId: activeChapterId || p.chapters[0]?.id,
    });
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    const meta = {
      title: title || 'Untitled Project',
      chapter: chapter || 'Chapter 1',
      genre,
      scene,
      characters: characters.split(',').map((c) => c.trim()).filter(Boolean),
      subgenreTags: subgenreTagsInput.split(',').map((c) => c.trim()).filter(Boolean),
      toneDescriptors: toneDescriptorsInput.split(',').map((c) => c.trim()).filter(Boolean),
      referenceAuthors: referenceAuthorsInput.split(',').map((c) => c.trim()).filter(Boolean),
    };

    if (mock) {
      clearPendingDraft();
      const chapterId = crypto.randomUUID();
      onBootstrap({
        metadata: meta,
        chapters: [
          {
            id: chapterId,
            title: meta.chapter,
            sortOrder: 0,
            rows: [makeSectionRow(DEFAULT_SECTION, false)],
          },
        ],
      });
      setPendingResume(null);
      return;
    }

    setBusy(true);
    try {
      const { document_id } = await createDocument({ title: meta.title });
      const pending = loadPendingDraft();

      if (!pending?.chapters?.length) {
        const { chapter_id } = await createDocumentChapter(document_id, {
          title: meta.chapter,
          sort_order: 0,
        });
        onBootstrap({
          metadata: { ...meta, documentId: document_id },
          chapters: [
            {
              id: chapter_id,
              title: meta.chapter,
              sortOrder: 0,
              rows: [makeSectionRow(DEFAULT_SECTION, false)],
            },
          ],
        });
        return;
      }

      const chapters: ChapterDoc[] = [];
      for (let i = 0; i < pending.chapters.length; i++) {
        const pc = pending.chapters[i];
        const { chapter_id } = await createDocumentChapter(document_id, {
          title: pc.title || `Chapter ${i + 1}`,
          sort_order: i,
        });
        chapters.push({
          id: chapter_id,
          title: pc.title || `Chapter ${i + 1}`,
          sortOrder: i,
          rows:
            pc.rows?.length > 0 ? pc.rows : [makeSectionRow(i === 0 ? DEFAULT_SECTION : '', false)],
        });
      }
      clearPendingDraft();
      const idx = pending.chapters.findIndex((c) => c.id === pending.activeChapterId);
      const activeChapterId =
        idx >= 0 && chapters[idx] ? chapters[idx].id : chapters[0]?.id ?? '';
      const mergedMeta = {
        ...pending.metadata,
        ...meta,
        documentId: document_id,
        title: meta.title.trim() || pending.metadata.title || 'Untitled',
        chapter: chapters[0]?.title ?? meta.chapter,
      };
      onBootstrap({
        metadata: mergedMeta,
        chapters,
        activeChapterId,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not create project');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-paper p-6 font-sans">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="max-w-md w-full bg-surface p-8 rounded-[2rem] shadow-sm border border-border"
      >
        <div className="flex items-center gap-3 text-ink mb-6">
          <div className="p-3 bg-accent/10 rounded-2xl text-accent">
            <Feather size={24} />
          </div>
          <div>
            <h1 className="font-serif font-semibold text-2xl tracking-tight">Welcome to Editr</h1>
            <p className="text-sm text-ink-light">Create a project or open an existing one.</p>
          </div>
        </div>

        {/* Tab switcher */}
        <div className="flex rounded-xl bg-overlay p-1 mb-6 gap-1">
          <button
            type="button"
            onClick={() => setTab('new')}
            className={`flex-1 flex items-center justify-center gap-2 py-2 rounded-lg text-sm font-medium transition-colors ${
              tab === 'new' ? 'bg-surface text-ink shadow-sm' : 'text-ink-light hover:text-ink'
            }`}
          >
            <Plus size={15} /> New project
          </button>
          <button
            type="button"
            onClick={() => setTab('load')}
            className={`flex-1 flex items-center justify-center gap-2 py-2 rounded-lg text-sm font-medium transition-colors ${
              tab === 'load' ? 'bg-surface text-ink shadow-sm' : 'text-ink-light hover:text-ink'
            }`}
          >
            <FolderOpen size={15} /> Open existing
          </button>
        </div>

        {error && (
          <p className="text-sm text-red-600 bg-red-50 dark:bg-red-950/40 px-3 py-2 rounded-lg mb-4">{error}</p>
        )}

        {tab === 'new' && mock && pendingResume?.chapters?.length ? (
          <button
            type="button"
            onClick={handleContinueDraft}
            className="w-full mb-4 py-3 rounded-xl border border-accent/40 bg-accent/5 text-accent text-sm font-medium hover:bg-accent/10 transition-colors"
          >
            Continue previous draft (mock session)
          </button>
        ) : null}

        {tab === 'new' && (
          <form onSubmit={handleSubmit} className="flex flex-col gap-5">
            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-medium text-ink">Project Title</label>
              <input
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="e.g. The Midnight Library"
                className="w-full px-4 py-2.5 rounded-xl bg-overlay border-transparent focus:bg-surface focus:border-accent focus:ring-2 focus:ring-accent/20 transition-all outline-none text-ink placeholder:text-ink-light/40"
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-medium text-ink">First chapter title</label>
              <input
                type="text"
                value={chapter}
                onChange={(e) => setChapter(e.target.value)}
                placeholder="e.g. Chapter 1"
                className="w-full px-4 py-2.5 rounded-xl bg-overlay border-transparent focus:bg-surface focus:border-accent focus:ring-2 focus:ring-accent/20 transition-all outline-none text-ink placeholder:text-ink-light/40"
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-medium text-ink">Genre</label>
              <input
                type="text"
                value={genre}
                onChange={(e) => setGenre(e.target.value)}
                placeholder="e.g. Sci-Fi, Memoir, Fantasy"
                className="w-full px-4 py-2.5 rounded-xl bg-overlay border-transparent focus:bg-surface focus:border-accent focus:ring-2 focus:ring-accent/20 transition-all outline-none text-ink placeholder:text-ink-light/40"
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-medium text-ink">
                Style targets <span className="text-ink-light font-normal">(optional, comma separated)</span>
              </label>
              <input
                type="text"
                value={subgenreTagsInput}
                onChange={(e) => setSubgenreTagsInput(e.target.value)}
                placeholder="Subgenre tags e.g. cozy mystery, epistolary"
                className="w-full px-4 py-2.5 rounded-xl bg-overlay border-transparent focus:bg-surface focus:border-accent focus:ring-2 focus:ring-accent/20 transition-all outline-none text-ink placeholder:text-ink-light/40"
              />
              <input
                type="text"
                value={toneDescriptorsInput}
                onChange={(e) => setToneDescriptorsInput(e.target.value)}
                placeholder="Tone descriptors e.g. wry, intimate"
                className="w-full px-4 py-2.5 rounded-xl bg-overlay border-transparent focus:bg-surface focus:border-accent focus:ring-2 focus:ring-accent/20 transition-all outline-none text-ink placeholder:text-ink-light/40"
              />
              <input
                type="text"
                value={referenceAuthorsInput}
                onChange={(e) => setReferenceAuthorsInput(e.target.value)}
                placeholder="Reference authors e.g. Ursula K. Le Guin"
                className="w-full px-4 py-2.5 rounded-xl bg-overlay border-transparent focus:bg-surface focus:border-accent focus:ring-2 focus:ring-accent/20 transition-all outline-none text-ink placeholder:text-ink-light/40"
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-medium text-ink">Scene Description</label>
              <textarea
                value={scene}
                onChange={(e) => setScene(e.target.value)}
                placeholder="Briefly describe the setting or goal of this chapter..."
                rows={3}
                className="w-full px-4 py-2.5 rounded-xl bg-overlay border-transparent focus:bg-surface focus:border-accent focus:ring-2 focus:ring-accent/20 transition-all outline-none text-ink placeholder:text-ink-light/40 resize-none"
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-medium text-ink">
                Characters <span className="text-ink-light font-normal">(comma separated)</span>
              </label>
              <input
                type="text"
                value={characters}
                onChange={(e) => setCharacters(e.target.value)}
                placeholder="e.g. Alice, Bob, The Cheshire Cat"
                className="w-full px-4 py-2.5 rounded-xl bg-overlay border-transparent focus:bg-surface focus:border-accent focus:ring-2 focus:ring-accent/20 transition-all outline-none text-ink placeholder:text-ink-light/40"
              />
            </div>

            <button
              type="submit"
              disabled={busy}
              className="mt-4 flex items-center justify-center gap-2 w-full py-3.5 rounded-xl bg-ink text-paper font-medium hover:bg-ink/90 transition-colors shadow-sm disabled:opacity-60"
            >
              {busy ? <Loader2 size={18} className="animate-spin" /> : <Sparkles size={18} />}
              Start Writing
            </button>
          </form>
        )}

        {tab === 'load' && (
          <div className="flex flex-col gap-3">
            {mock && (
              <p className="text-sm text-ink-light text-center py-4">
                Mock mode is enabled — no documents to load. Set <code className="bg-overlay px-1 rounded">VITE_USE_MOCK_API=false</code> to use real projects.
              </p>
            )}
            {!mock && loadingDocs && (
              <div className="flex justify-center py-6">
                <Loader2 className="animate-spin text-accent" size={22} />
              </div>
            )}
            {!mock && !loadingDocs && docs.length === 0 && (
              <p className="text-sm text-ink-light text-center py-4">No projects found. Create one first.</p>
            )}
            {!mock && !loadingDocs && docs.map((doc) => (
              <div
                key={doc.document_id}
                className="flex items-stretch gap-2 rounded-xl bg-overlay border border-transparent hover:border-border/60 transition-colors"
              >
                <button
                  type="button"
                  disabled={loadingDocId === doc.document_id || deletingDocId === doc.document_id}
                  onClick={() => handleLoadDoc(doc)}
                  className="flex-1 min-w-0 flex items-center justify-between gap-3 px-4 py-3 text-left rounded-xl hover:bg-border/80 transition-colors disabled:opacity-60"
                >
                  <div className="min-w-0">
                    <p className="font-medium text-ink truncate">{doc.title || 'Untitled'}</p>
                    <p className="text-xs text-ink-light mt-0.5">
                      {new Date(doc.created_at).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })}
                    </p>
                  </div>
                  {loadingDocId === doc.document_id ? (
                    <Loader2 size={16} className="animate-spin text-accent shrink-0" />
                  ) : (
                    <FolderOpen size={16} className="text-ink-light shrink-0" aria-hidden />
                  )}
                </button>
                <div className="flex items-center pr-2 py-2">
                  <button
                    type="button"
                    aria-label={`Delete ${doc.title || 'Untitled'}`}
                    disabled={loadingDocId === doc.document_id || deletingDocId === doc.document_id}
                    onClick={(e) => handleDeleteDoc(doc, e)}
                    className="shrink-0 p-2.5 rounded-lg text-ink-light hover:text-rose-600 hover:bg-rose-500/10 transition-colors disabled:opacity-50"
                  >
                    {deletingDocId === doc.document_id ? (
                      <Loader2 size={16} className="animate-spin text-accent" />
                    ) : (
                      <Trash2 size={16} />
                    )}
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </motion.div>
    </div>
  );
}
