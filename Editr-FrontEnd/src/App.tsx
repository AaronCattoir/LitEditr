import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import {
  Plus,
  Feather,
  Maximize2,
  Minimize2,
  Settings as SettingsIcon,
  BookMarked,
  Save,
  Sparkles,
  Loader2,
  Moon,
  Sun,
  ArrowLeft,
  Upload,
} from 'lucide-react';
import { Section } from './components/Section';
import {
  type ProjectMetadata,
  type ChapterDoc,
  type SectionData,
  type ProjectBootstrap,
  type EditorialReportPayload,
  type RuntimeProvidersResponse,
  useMockApi,
  submitToLanggraphMock,
  submitAllToLanggraphMock,
  createDocumentChapter,
  createRevision,
  postAnalyzeRevision,
  pollJobUntilDone,
  postQuickCoach,
  genreIntentionPayloadFromMetadata,
  buildJudgmentMap,
  makeSectionRow,
  updateDocumentChapter,
  getLatestRevisionAnalysis,
  getDocumentManuscript,
  getRuntimeProviders,
  resolveSelectableLlmProvider,
} from './lib/api';
import { ProjectInit } from './components/ProjectInit';
import { SettingsPanel } from './components/SettingsPanel';
import { StoryAnalysisPanel } from './components/StoryAnalysisPanel';
import { defaultStoryManuscriptFilename, downloadMarkdownFile } from './lib/analysisExport';
import { ChapterSidebar } from './components/ChapterSidebar';
import { motion, AnimatePresence } from 'motion/react';
import { cn } from './lib/utils';
import {
  buildManuscriptAndChunks,
  getManuscriptChunkText,
  parseManuscriptToChapters,
  validateManuscriptBuild,
  splitOnSceneMarkers,
} from './lib/manuscriptSerialize';
import { mergeMetadataFromAnalysisReport } from './lib/storyWideMetadata';
import {
  DRAFT_VERSION,
  loadDraft,
  saveDraft,
  savePendingDraft,
  loadPendingDraft,
} from './lib/draftStorage';
import type { RestorePayload } from './lib/api';

function distributeSectionUpdates(chapters: ChapterDoc[], flatUpdated: SectionData[]): ChapterDoc[] {
  let idx = 0;
  return chapters.map((ch) => ({
    ...ch,
    rows: ch.rows.map((r) => {
      const u = flatUpdated[idx++];
      return u ? { ...r, ...u } : r;
    }),
  }));
}

function applyJudgmentsToChapters(
  chapters: ChapterDoc[],
  map: Map<string, import('./lib/api').GraphChunkJudgment>,
): ChapterDoc[] {
  return chapters.map((ch) => ({
    ...ch,
    rows: ch.rows.map((r) => {
      const g = map.get(r.id);
      return g ? { ...r, graphAdvice: g } : { ...r, graphAdvice: undefined };
    }),
  }));
}

/** Slim control to insert a section above the first block or between two scenes. */
function SectionInsertGap({
  isFocusMode,
  onInsert,
  label = 'Add section',
}: {
  isFocusMode: boolean;
  onInsert: () => void;
  label?: string;
}) {
  if (isFocusMode) return null;
  return (
    <div className="group relative flex justify-center py-2 -my-1">
      <div className="absolute inset-x-8 top-1/2 h-px bg-border/50 opacity-0 transition-opacity group-hover:opacity-100 pointer-events-none" />
      <button
        type="button"
        onClick={onInsert}
        className="relative z-10 flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium font-sans text-ink-light bg-paper hover:bg-overlay hover:text-accent border border-border/60 shadow-sm transition-colors"
      >
        <Plus size={14} className="shrink-0" />
        {label}
      </button>
    </div>
  );
}

export default function App() {
  const mock = useMockApi();
  const [bootstrap, setBootstrap] = useState<ProjectBootstrap | null>(null);
  const [metadata, setMetadata] = useState<ProjectMetadata | null>(null);
  const [chapters, setChapters] = useState<ChapterDoc[]>([]);
  const [activeChapterId, setActiveChapterId] = useState('');
  const [isFocusMode, setIsFocusMode] = useState(false);
  const [rightPanel, setRightPanel] = useState<'none' | 'settings' | 'story'>('none');
  const [latestReport, setLatestReport] = useState<EditorialReportPayload | null>(null);
  const [latestAnalysisKind, setLatestAnalysisKind] = useState<string | null>(null);
  const [latestAnalysisFromFallback, setLatestAnalysisFromFallback] = useState(false);
  const [latestRunRevisionId, setLatestRunRevisionId] = useState<string | null>(null);
  const [isSubmittingAll, setIsSubmittingAll] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isDarkMode, setIsDarkMode] = useState(false);
  const [submitPhase, setSubmitPhase] = useState<string | null>(null);
  const [runtimeProviders, setRuntimeProviders] = useState<RuntimeProvidersResponse | null>(null);
  const [runtimeProvidersError, setRuntimeProvidersError] = useState<string | null>(null);
  const draftHydrated = useRef(false);
  const mockDraftHydrated = useRef(false);
  const submitAbortRef = useRef<AbortController | null>(null);
  const importInputRef = useRef<HTMLInputElement>(null);

  const MAX_IMPORT_BYTES = 5 * 1024 * 1024;

  useEffect(() => {
    if (!bootstrap) return;
    setMetadata(bootstrap.metadata);
    setChapters(bootstrap.chapters);
    setActiveChapterId(bootstrap.activeChapterId ?? bootstrap.chapters[0]?.id ?? '');
  }, [bootstrap]);

  useEffect(() => {
    if (mock || !bootstrap) {
      setRuntimeProviders(null);
      setRuntimeProvidersError(null);
      return;
    }
    let cancelled = false;
    void getRuntimeProviders()
      .then((r) => {
        if (!cancelled) {
          setRuntimeProviders(r);
          setRuntimeProvidersError(null);
        }
      })
      .catch((e) => {
        if (!cancelled) {
          setRuntimeProviders(null);
          setRuntimeProvidersError(e instanceof Error ? e.message : 'Failed to load providers');
        }
      });
    return () => {
      cancelled = true;
    };
  }, [mock, bootstrap]);

  useEffect(() => {
    if (mock || !runtimeProviders || !bootstrap) return;
    setMetadata((m) => {
      if (!m) return m;
      const resolved = resolveSelectableLlmProvider(runtimeProviders, m.llmProvider);
      const next = resolved ?? undefined;
      if (next === m.llmProvider) return m;
      return { ...m, llmProvider: next };
    });
  }, [mock, runtimeProviders, bootstrap]);

  /** Same resolution as assertProviderReadyForApi; use in API bodies so provider matches server capabilities. */
  const effectiveLlmProviderForRequests = useMemo(() => {
    if (mock || !runtimeProviders) return null;
    return resolveSelectableLlmProvider(runtimeProviders, metadata?.llmProvider) ?? null;
  }, [mock, runtimeProviders, metadata?.llmProvider]);

  const assertProviderReadyForApi = useCallback((): boolean => {
    if (mock) return true;
    if (runtimeProvidersError) {
      alert(
        `Could not load LLM provider status: ${runtimeProvidersError}\n\nCheck that the API is reachable.`,
      );
      return false;
    }
    if (!runtimeProviders) {
      alert('LLM provider status is still loading. Please wait a moment and try again.');
      return false;
    }
    const effectiveProvider = resolveSelectableLlmProvider(
      runtimeProviders,
      metadata?.llmProvider,
    );
    if (!effectiveProvider) {
      alert(
        'No LLM provider is configured on the server. Add OPENAI_API_KEY and/or GEMINI_API_KEY (or GOOGLE_API_KEY) to the server environment, then refresh this page.',
      );
      return false;
    }
    return true;
  }, [mock, runtimeProviders, runtimeProvidersError, metadata?.llmProvider]);

  const refreshLatestAnalysis = useCallback(async (revisionIdOverride?: string) => {
    const rev = revisionIdOverride ?? metadata?.revisionId;
    if (mock || !rev) return;
    try {
      const latest = await getLatestRevisionAnalysis(rev);
      setLatestReport(latest.report);
      setLatestAnalysisKind(latest.analysis_kind ?? null);
      setLatestAnalysisFromFallback(Boolean(latest.from_fallback));
      setLatestRunRevisionId(latest.run_revision_id ?? null);
      setMetadata((m) =>
        m
          ? mergeMetadataFromAnalysisReport(
              { ...m, runId: latest.run_id ?? undefined },
              latest.report,
            )
          : m,
      );
    } catch {
      setLatestReport(null);
      setLatestAnalysisKind(null);
      setLatestAnalysisFromFallback(false);
      setLatestRunRevisionId(null);
    }
  }, [mock, metadata?.revisionId]);

  const recoverTimedOutAnalysis = useCallback(
    async (revisionId: string): Promise<boolean> => {
      try {
        const latest = await getLatestRevisionAnalysis(revisionId);
        // We only auto-recover from the just-submitted revision; ignore fallback runs.
        if (!latest.report || latest.from_fallback) return false;
        const runRevisionId = latest.run_revision_id ?? revisionId;
        if (runRevisionId !== revisionId) return false;

        const map = buildJudgmentMap(latest.report);
        setChapters((cs) => applyJudgmentsToChapters(cs, map));
        setMetadata((m) =>
          m
            ? mergeMetadataFromAnalysisReport(
                {
                  ...m,
                  revisionId,
                  runId: latest.run_id ?? undefined,
                  analyzedRevisionId: revisionId,
                },
                latest.report,
              )
            : m,
        );
        await refreshLatestAnalysis(revisionId);
        return true;
      } catch {
        return false;
      }
    },
    [refreshLatestAnalysis],
  );

  useEffect(() => {
    if (!metadata?.revisionId || mock) {
      setLatestReport(null);
      setLatestAnalysisKind(null);
      setLatestAnalysisFromFallback(false);
      setLatestRunRevisionId(null);
      return;
    }
    const id = setTimeout(() => {
      void refreshLatestAnalysis();
    }, 0);
    return () => clearTimeout(id);
  }, [metadata?.revisionId, mock, refreshLatestAnalysis]);

  useEffect(() => {
    if (rightPanel !== 'story' || mock || !metadata?.revisionId) return;
    void refreshLatestAnalysis();
  }, [rightPanel, mock, metadata?.revisionId, refreshLatestAnalysis]);

  // Keep per-section graph advice in sync with the latest fetched report.
  // This ensures section-level extras (narrative intent / emotional register)
  // appear even when they arrive on a follow-up latest-analysis fetch.
  useEffect(() => {
    if (mock || !latestReport) return;
    const map = buildJudgmentMap(latestReport);
    setChapters((cs) => applyJudgmentsToChapters(cs, map));
  }, [mock, latestReport]);

  /** Resolve head revision from API when we have a document but no revision id (e.g. resumed local draft). */
  useEffect(() => {
    if (!metadata?.documentId || mock || metadata.revisionId) return;
    let cancelled = false;
    void (async () => {
      try {
        const ms = await getDocumentManuscript(metadata.documentId!);
        const head = ms.current_revision?.revision_id;
        if (cancelled || !head) return;
        setMetadata((m) => (m ? { ...m, revisionId: head } : m));
        const latest = await getLatestRevisionAnalysis(head);
        if (cancelled) return;
        setLatestReport(latest.report);
        setLatestAnalysisKind(latest.analysis_kind ?? null);
        setLatestAnalysisFromFallback(Boolean(latest.from_fallback));
        setLatestRunRevisionId(latest.run_revision_id ?? null);
        setMetadata((m) =>
          m
            ? mergeMetadataFromAnalysisReport(
                { ...m, runId: latest.run_id ?? undefined },
                latest.report,
              )
            : m,
        );
      } catch {
        /* leave panel empty until save / explicit refresh */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [metadata?.documentId, metadata?.revisionId, mock]);

  const handleExportStoryManuscript = useCallback(() => {
    const built = buildManuscriptAndChunks(chapters);
    const v = validateManuscriptBuild(built);
    if (!v.ok) {
      alert('message' in v ? v.message : 'Manuscript validation failed.');
      return;
    }
    downloadMarkdownFile(
      defaultStoryManuscriptFilename({
        title: metadata?.title ?? '',
        documentId: metadata?.documentId,
      }),
      built.documentText,
    );
  }, [chapters, metadata?.title, metadata?.documentId]);

  useEffect(() => {
    if (!metadata?.documentId || mock || draftHydrated.current) return;
    draftHydrated.current = true;
    const d = loadDraft(metadata.documentId);
    if (d) {
      setChapters(d.chapters);
      setActiveChapterId(d.activeChapterId);
      // Keep server-backed revision/run ids from bootstrap; draft only had local editor state.
      setMetadata((m) => (m ? { ...d.metadata, ...m } : d.metadata));
    }
  }, [metadata?.documentId, mock]);

  useEffect(() => {
    if (!bootstrap || !mock || mockDraftHydrated.current) return;
    mockDraftHydrated.current = true;
    const p = loadPendingDraft();
    if (p?.chapters?.length) {
      setChapters(p.chapters);
      setActiveChapterId(p.activeChapterId);
      setMetadata(p.metadata);
    }
  }, [bootstrap, mock]);

  useEffect(() => {
    const ch = chapters.find((c) => c.id === activeChapterId);
    if (ch) setMetadata((m) => (m ? { ...m, chapter: ch.title } : m));
  }, [activeChapterId, chapters]);

  useEffect(() => {
    if (!metadata?.documentId || mock) return;
    const t = setTimeout(() => {
      saveDraft(metadata.documentId!, {
        version: DRAFT_VERSION,
        chapters,
        activeChapterId,
        metadata: {
          ...metadata,
          revisionId: metadata.revisionId,
          runId: metadata.runId,
          analyzedRevisionId: metadata.analyzedRevisionId,
        },
      });
    }, 1500);
    return () => clearTimeout(t);
  }, [chapters, activeChapterId, metadata, mock]);

  useEffect(() => {
    if (!mock || !metadata || metadata.documentId) return;
    const t = setTimeout(() => {
      savePendingDraft({
        version: DRAFT_VERSION,
        chapters,
        activeChapterId,
        metadata: {
          ...metadata,
          revisionId: metadata.revisionId,
          runId: metadata.runId,
          analyzedRevisionId: metadata.analyzedRevisionId,
        },
      });
    }, 1500);
    return () => clearTimeout(t);
  }, [chapters, activeChapterId, metadata, mock]);

  useEffect(() => {
    if (isDarkMode) {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
  }, [isDarkMode]);

  const toggleFocusMode = () => {
    if (!isFocusMode) {
      setRightPanel('none');
      document.documentElement.requestFullscreen().catch(() => {});
    } else {
      document.exitFullscreen().catch(() => {});
    }
    setIsFocusMode(!isFocusMode);
  };

  useEffect(() => {
    const handleFullscreenChange = () => {
      if (!document.fullscreenElement) {
        setIsFocusMode(false);
      }
    };
    document.addEventListener('fullscreenchange', handleFullscreenChange);
    return () => document.removeEventListener('fullscreenchange', handleFullscreenChange);
  }, []);

  const activeRows = chapters.find((c) => c.id === activeChapterId)?.rows ?? [];

  const updateActiveRows = useCallback((updater: (rows: SectionData[]) => SectionData[]) => {
    setChapters((prev) =>
      prev.map((c) => (c.id === activeChapterId ? { ...c, rows: updater(c.rows) } : c)),
    );
  }, [activeChapterId]);

  const handleChange = useCallback(
    (id: string, content: string) => {
      updateActiveRows((rows) => rows.map((s) => (s.id === id ? { ...s, content } : s)));
    },
    [updateActiveRows],
  );

  const handleToggleEdit = useCallback(
    (id: string, isEditing: boolean) => {
      updateActiveRows((rows) => rows.map((s) => (s.id === id ? { ...s, isEditing } : s)));
    },
    [updateActiveRows],
  );

  const handleDelete = useCallback(
    (id: string) => {
      updateActiveRows((rows) => rows.filter((s) => s.id !== id));
    },
    [updateActiveRows],
  );

  /** Replace a section with multiple new ones (split-on-tilde). */
  const handleSplitSection = useCallback(
    (id: string, parts: string[]) => {
      updateActiveRows((rows) => {
        const idx = rows.findIndex((s) => s.id === id);
        if (idx === -1) return rows;
        const newRows = parts.map((content) => makeSectionRow(content, false));
        const copy = [...rows];
        copy.splice(idx, 1, ...newRows);
        return copy;
      });
    },
    [updateActiveRows],
  );

  /** Insert a new section after `afterId`, or at the beginning of the chapter if `afterId` is null. */
  const handleInsertSectionAfter = useCallback(
    (afterId: string | null) => {
      updateActiveRows((rows) => {
        const newRow = makeSectionRow('', true);
        if (afterId === null) return [newRow, ...rows];
        const idx = rows.findIndex((s) => s.id === afterId);
        if (idx === -1) return [...rows, newRow];
        const copy = [...rows];
        copy.splice(idx + 1, 0, newRow);
        return copy;
      });
    },
    [updateActiveRows],
  );

  const handleMoveSection = useCallback(
    (id: string, dir: 'up' | 'down') => {
      updateActiveRows((rows) => {
        const idx = rows.findIndex((s) => s.id === id);
        if (idx === -1) return rows;
        const j = dir === 'up' ? idx - 1 : idx + 1;
        if (j < 0 || j >= rows.length) return rows;
        const copy = [...rows];
        [copy[idx], copy[j]] = [copy[j], copy[idx]];
        return copy;
      });
    },
    [updateActiveRows],
  );

  const handleRenameChapter = async (chapterId: string, title: string) => {
    setChapters((prev) => prev.map((c) => (c.id === chapterId ? { ...c, title } : c)));
    if (chapterId === activeChapterId) {
      setMetadata((m) => (m ? { ...m, chapter: title } : m));
    }
    if (!mock && metadata?.documentId) {
      try {
        await updateDocumentChapter(chapterId, { title });
      } catch (e) {
        console.error(e);
        alert(e instanceof Error ? e.message : 'Could not rename chapter');
      }
    }
  };

  const handleImportFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    if (file.size > MAX_IMPORT_BYTES) {
      alert('File is too large (max 5 MB).');
      return;
    }
    try {
      const text = await file.text();
      const hasDelims = text.includes('<<<EDITR_CHAPTER');
      if (hasDelims) {
        const parsed = parseManuscriptToChapters(text);
        setChapters(parsed);
        const first = parsed[0];
        if (first) {
          setActiveChapterId(first.id);
          setMetadata((m) => (m ? { ...m, chapter: first.title } : m));
        }
        return;
      }
      const parts = splitOnSceneMarkers(text);
      if (parts.length > 1) {
        setChapters((prev) =>
          prev.map((c) =>
            c.id === activeChapterId
              ? { ...c, rows: parts.map((content) => makeSectionRow(content, false)) }
              : c,
          ),
        );
        return;
      }
      setChapters((prev) =>
        prev.map((c) =>
          c.id === activeChapterId ? { ...c, rows: [makeSectionRow(text, false)] } : c,
        ),
      );
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Could not read file');
    }
  };

  const handleBackToProjects = () => {
    if (!window.confirm('Leave this project? Unsaved changes in the editor may be lost.')) return;
    submitAbortRef.current?.abort();
    draftHydrated.current = false;
    mockDraftHydrated.current = false;
    setBootstrap(null);
  };

  const handleMetadataUpdate = (m: ProjectMetadata) => {
    setMetadata(m);
    setChapters((prev) =>
      prev.map((c) => (c.id === activeChapterId ? { ...c, title: m.chapter } : c)),
    );
  };

  const handleAddChapter = async () => {
    const title = `Chapter ${chapters.length + 1}`;
    if (!mock && metadata?.documentId) {
      try {
        const { chapter_id } = await createDocumentChapter(metadata.documentId, {
          title,
          sort_order: chapters.length,
        });
        setChapters((prev) => [
          ...prev,
          { id: chapter_id, title, sortOrder: chapters.length, rows: [makeSectionRow('', true)] },
        ]);
        setActiveChapterId(chapter_id);
      } catch (e) {
        console.error(e);
        alert(e instanceof Error ? e.message : 'Could not create chapter');
      }
      return;
    }
    const id = crypto.randomUUID();
    setChapters((prev) => [
      ...prev,
      { id, title, sortOrder: prev.length, rows: [makeSectionRow('', true)] },
    ]);
    setActiveChapterId(id);
  };

  const handleSubmit = async (id: string) => {
    updateActiveRows((rows) => rows.map((s) => (s.id === id ? { ...s, status: 'submitting' } : s)));

    try {
      const row = activeRows.find((s) => s.id === id);
      if (!row) {
        updateActiveRows((rows) => rows.map((s) => (s.id === id ? { ...s, status: 'draft' } : s)));
        return;
      }

      if (mock) {
        const text = await submitToLanggraphMock(row.content);
        updateActiveRows((rows) =>
          rows.map((s) =>
            s.id === id
              ? {
                  ...s,
                  status: 'coached',
                  quickCoach: { headline: 'Quick coach', bullets: [text], try_next: null },
                }
              : s,
          ),
        );
        return;
      }

      if (!metadata?.revisionId) {
        updateActiveRows((rows) => rows.map((s) => (s.id === id ? { ...s, status: 'draft' } : s)));
        alert('Save your manuscript first so the coach can attach to a revision.');
        return;
      }

      if (!assertProviderReadyForApi()) {
        updateActiveRows((rows) => rows.map((s) => (s.id === id ? { ...s, status: 'draft' } : s)));
        return;
      }

      const built = buildManuscriptAndChunks(chapters);
      const chunkSlice = getManuscriptChunkText(chapters, id);
      const alignedRunId =
        metadata.analyzedRevisionId === metadata.revisionId ? metadata.runId ?? null : null;
      const quickBody = {
        chunk_id: id,
        run_id: alignedRunId,
        focus: null,
        ...genreIntentionPayloadFromMetadata(metadata),
        title: metadata.title,
        chunks: built.chunks,
        short_story_single_chapter: Boolean(metadata.shortStorySingleChapter),
        provider: effectiveLlmProviderForRequests,
        ...(chunkSlice != null ? { current_chunk_text: chunkSlice } : {}),
      };
      
      let res = await postQuickCoach(metadata.revisionId, quickBody);
      if (res.kind === 'run_revision_mismatch') {
        res = await postQuickCoach(metadata.revisionId, { ...quickBody, run_id: null });
      }
      
      if (res.kind === 'run_revision_mismatch') {
        updateActiveRows((rows) => rows.map((s) => (s.id === id ? { ...s, status: 'draft' } : s)));
        alert(res.error ?? 'Run no longer matches this revision. Try Submit All or save again.');
        return;
      }
      
      if (res.kind === 'queued') {
        updateActiveRows((rows) =>
          rows.map((s) =>
            s.id === id
              ? {
                  ...s,
                  status: 'draft',
                  quickCoach: {
                    headline: 'Analysis queued',
                    bullets: [
                      'A background analysis job was queued for this revision. Wait for it to finish, then try sparkle again.',
                    ],
                    try_next: null,
                  },
                }
              : s,
          ),
        );
        return;
      }
      
      if (res.kind === 'oob') {
        updateActiveRows((rows) => rows.map((s) => (s.id === id ? { ...s, status: 'draft' } : s)));
        alert(
          `${res.error ?? 'This section changed too much since the last analysis.'}\n\n` +
            `Character delta: ${res.delta_chars ?? '?'} (threshold ${res.threshold_chars ?? '?'}).\n` +
            `Run Submit All or use “Reanalyze this section” on the section.`,
        );
        return;
      }
      
      if (res.kind === 'advice' && res.run_id) {
        setMetadata((m) =>
          m
            ? {
                ...m,
                runId: res.run_id ?? undefined,
                analyzedRevisionId: res.revision_id ?? metadata.revisionId ?? m.analyzedRevisionId,
              }
            : m,
        );
      }
      
      updateActiveRows((rows) =>
        rows.map((s) =>
          s.id === id ? { ...s, status: 'coached', quickCoach: res.advice } : s,
        ),
      );
    } catch (e) {
      console.error(e);
      updateActiveRows((rows) => rows.map((s) => (s.id === id ? { ...s, status: 'draft' } : s)));
      alert(e instanceof Error ? e.message : 'Quick coach failed');
    }
  };

  const handleReanalyzeSection = async (id: string) => {
    if (!metadata?.documentId || !metadata.revisionId || !metadata.runId) {
      alert('Save the manuscript and run a full analysis first, then you can reanalyze one section.');
      return;
    }
    const built = buildManuscriptAndChunks(chapters);
    const v = validateManuscriptBuild(built);
    if (!v.ok) {
      alert('message' in v ? v.message : 'Manuscript validation failed.');
      return;
    }
    if (mock) {
      alert('Partial reanalyze is not available in mock mode.');
      return;
    }
    if (!assertProviderReadyForApi()) return;
    setIsSubmittingAll(true);
    submitAbortRef.current?.abort();
    submitAbortRef.current = new AbortController();
    const { signal } = submitAbortRef.current;
    let submittedRevisionId: string | null = null;
    setSubmitPhase('Saving revision…');
    try {
      const baseRunId = metadata.runId;
      const { revision_id } = await createRevision(metadata.documentId, {
        text: built.documentText,
        parent_revision_id: metadata.revisionId,
      });
      submittedRevisionId = revision_id;
      setMetadata((m) =>
        m
          ? {
              ...m,
              revisionId: revision_id,
              runId: undefined,
              analyzedRevisionId: undefined,
            }
          : m,
      );

      setSubmitPhase('Queueing section reanalysis…');
      const { job_id } = await postAnalyzeRevision(revision_id, {
        ...genreIntentionPayloadFromMetadata(metadata),
        title: metadata.title,
        chunks: built.chunks,
        base_run_id: baseRunId,
        only_chunk_ids: [id],
        short_story_single_chapter: Boolean(metadata.shortStorySingleChapter),
        provider: effectiveLlmProviderForRequests,
      });
      setSubmitPhase('Reanalyzing section — this may take a minute…');
      const job = await pollJobUntilDone(job_id, { signal });
      const result = job.result;
      if (!result?.report) throw new Error('Job succeeded but report missing');
      const map = buildJudgmentMap(result.report);
      setChapters((cs) => applyJudgmentsToChapters(cs, map));
      setMetadata((m) =>
        m
          ? mergeMetadataFromAnalysisReport(
              {
                ...m,
                revisionId: result.revision_id,
                runId: result.run_id,
                analyzedRevisionId: result.revision_id,
              },
              result.report,
            )
          : m,
      );
      await refreshLatestAnalysis(result.revision_id);
    } catch (e) {
      if (e instanceof Error && e.name === 'AbortError') return;
      if (
        e instanceof Error &&
        e.message === 'job polling timed out' &&
        submittedRevisionId
      ) {
        setSubmitPhase('Polling timed out — checking latest analysis once…');
        const recovered = await recoverTimedOutAnalysis(submittedRevisionId);
        if (recovered) return;
      }
      console.error(e);
      alert(e instanceof Error ? e.message : 'Section reanalysis failed');
    } finally {
      setIsSubmittingAll(false);
      setSubmitPhase(null);
    }
  };

  const handleSave = async () => {
    const built = buildManuscriptAndChunks(chapters);
    const v = validateManuscriptBuild(built);
    if (!v.ok) {
      alert('message' in v ? v.message : 'Manuscript validation failed.');
      return;
    }
    if (mock) {
      setIsSaving(true);
      setTimeout(() => setIsSaving(false), 800);
      return;
    }
    if (!metadata?.documentId) return;
    setIsSaving(true);
    try {
      const { documentText } = built;
      const { revision_id } = await createRevision(metadata.documentId, {
        text: documentText,
        parent_revision_id: metadata.revisionId ?? null,
      });
      setMetadata((m) =>
        m
          ? {
              ...m,
              revisionId: revision_id,
              runId: undefined,
              analyzedRevisionId: undefined,
            }
          : m,
      );
    } catch (e) {
      console.error(e);
      alert(e instanceof Error ? e.message : 'Save failed');
    } finally {
      setIsSaving(false);
    }
  };

  const handleSubmitAll = async () => {
    if (!metadata) return;
    const built = buildManuscriptAndChunks(chapters);
    const v = validateManuscriptBuild(built);
    if (!v.ok) {
      alert('message' in v ? v.message : 'Manuscript validation failed.');
      return;
    }
    setIsSubmittingAll(true);
    submitAbortRef.current?.abort();
    submitAbortRef.current = new AbortController();
    const { signal } = submitAbortRef.current;
    let submittedRevisionId: string | null = null;
    try {
      if (mock) {
        setSubmitPhase('Running mock analysis…');
        const flat = chapters.flatMap((c) => c.rows);
        const result = await submitAllToLanggraphMock(flat, metadata);
        setChapters(distributeSectionUpdates(chapters, result.sections));
        setMetadata(result.metadata);
        return;
      }
      if (!metadata.documentId) {
        alert('Missing document');
        return;
      }
      if (!assertProviderReadyForApi()) return;
      setSubmitPhase('Saving revision…');
      const { revision_id } = await createRevision(metadata.documentId, {
        text: built.documentText,
        parent_revision_id: metadata.revisionId ?? null,
      });
      submittedRevisionId = revision_id;
      setMetadata((m) =>
        m
          ? {
              ...m,
              revisionId: revision_id,
              runId: undefined,
              analyzedRevisionId: undefined,
            }
          : m,
      );

      setSubmitPhase('Queueing analysis…');
      const { job_id } = await postAnalyzeRevision(revision_id, {
        ...genreIntentionPayloadFromMetadata(metadata),
        title: metadata.title,
        chunks: built.chunks,
        short_story_single_chapter: Boolean(metadata.shortStorySingleChapter),
        provider: effectiveLlmProviderForRequests,
      });
      setSubmitPhase('Analysis running — this may take a minute…');
      const job = await pollJobUntilDone(job_id, { signal });
      const result = job.result;
      if (!result?.report) throw new Error('Job succeeded but report missing');
      const map = buildJudgmentMap(result.report);
      setChapters((cs) => applyJudgmentsToChapters(cs, map));
      setMetadata((m) =>
        m
          ? mergeMetadataFromAnalysisReport(
              {
                ...m,
                revisionId: result.revision_id,
                runId: result.run_id,
                analyzedRevisionId: result.revision_id,
              },
              result.report,
            )
          : m,
      );
      await refreshLatestAnalysis(result.revision_id);
    } catch (e) {
      if (e instanceof Error && e.name === 'AbortError') return;
      if (
        e instanceof Error &&
        e.message === 'job polling timed out' &&
        submittedRevisionId
      ) {
        setSubmitPhase('Polling timed out — checking latest analysis once…');
        const recovered = await recoverTimedOutAnalysis(submittedRevisionId);
        if (recovered) return;
      }
      console.error(e);
      alert(e instanceof Error ? e.message : 'Submit All failed');
    } finally {
      setIsSubmittingAll(false);
      setSubmitPhase(null);
    }
  };

  const handleRestoreBookmark = (payload: RestorePayload) => {
    const parsed = parseManuscriptToChapters(payload.revision.full_text);
    setChapters(parsed);
    const first = parsed[0];
    setActiveChapterId(first?.id ?? '');
    setMetadata((m) =>
      m
        ? {
            ...m,
            chapter: first?.title ?? m.chapter,
            revisionId: payload.revision.revision_id,
            runId: payload.bookmark.run_id ?? m.runId,
            analyzedRevisionId: payload.revision.revision_id,
          }
        : m,
    );
  };

  if (!bootstrap || !metadata) {
    return <ProjectInit onBootstrap={setBootstrap} />;
  }

  return (
    <div className="min-h-screen flex font-sans selection:bg-accent/20 bg-paper overflow-hidden">
      {!isFocusMode && (
        <ChapterSidebar
          chapters={chapters}
          activeChapterId={activeChapterId}
          onSelect={setActiveChapterId}
          onAddChapter={handleAddChapter}
          onRenameChapter={handleRenameChapter}
          isFocusMode={isFocusMode}
        />
      )}

      <div
        className={cn(
          'flex-1 flex flex-col h-screen overflow-y-auto transition-all duration-500',
          rightPanel !== 'none' && !isFocusMode ? 'mr-80' : '',
        )}
      >
        <header
          className={cn(
            'sticky top-0 z-10 bg-paper/90 backdrop-blur-md border-b border-border transition-all duration-500',
            isFocusMode ? 'opacity-0 hover:opacity-100 -translate-y-full hover:translate-y-0' : 'opacity-100 translate-y-0',
          )}
        >
          <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
            <div className="flex items-center gap-2 text-ink min-w-0">
              <button
                type="button"
                onClick={handleBackToProjects}
                className="p-2 hover:bg-overlay rounded-full shrink-0 text-ink-light hover:text-ink transition-colors"
                title="Back to projects"
              >
                <ArrowLeft size={20} />
              </button>
              <input
                ref={importInputRef}
                type="file"
                accept=".txt,.md,text/plain,text/markdown"
                className="hidden"
                onChange={handleImportFile}
              />
              <Feather className="text-accent shrink-0" size={20} />
              <h1 className="font-serif font-semibold text-xl tracking-tight truncate">
                {metadata.title}{' '}
                <span className="text-ink-light/50 font-normal text-base ml-2">{metadata.chapter}</span>
              </h1>
            </div>
            <div className="flex items-center gap-2 text-sm text-ink-light shrink-0">
              <button
                type="button"
                onClick={() => importInputRef.current?.click()}
                className="flex items-center gap-1.5 px-3 py-1.5 hover:bg-overlay rounded-lg transition-colors font-medium text-ink"
                title="Import a .txt or .md file (replaces the active chapter, or full manuscript if delimiters are present)"
              >
                <Upload size={16} />
                Import
              </button>

              <button
                onClick={handleSave}
                disabled={isSaving}
                className="flex items-center gap-1.5 px-3 py-1.5 hover:bg-overlay rounded-lg transition-colors font-medium text-ink disabled:opacity-50"
              >
                {isSaving ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
                Save
              </button>

              <button
                onClick={handleSubmitAll}
                disabled={isSubmittingAll}
                className="flex items-center gap-1.5 px-4 py-1.5 bg-accent text-paper hover:bg-accent-hover rounded-full transition-colors font-medium disabled:opacity-50 shadow-sm ml-2"
              >
                {isSubmittingAll ? <Loader2 size={16} className="animate-spin" /> : <Sparkles size={16} />}
                Submit All
              </button>

              <div className="w-px h-5 bg-border mx-2" />

              <button
                onClick={() => setIsDarkMode(!isDarkMode)}
                className="p-2 hover:bg-overlay rounded-full transition-colors"
                title={isDarkMode ? 'Light Mode' : 'Dark Mode'}
                type="button"
              >
                {isDarkMode ? <Sun size={18} /> : <Moon size={18} />}
              </button>

              <button
                onClick={toggleFocusMode}
                className="p-2 hover:bg-overlay rounded-full transition-colors"
                title={isFocusMode ? 'Exit Focus Mode' : 'Enter Focus Mode'}
                type="button"
              >
                {isFocusMode ? <Minimize2 size={18} /> : <Maximize2 size={18} />}
              </button>
              {!isFocusMode && (
                <>
                  <button
                    onClick={() => setRightPanel((p) => (p === 'story' ? 'none' : 'story'))}
                    className={cn(
                      'p-2 hover:bg-overlay rounded-full transition-colors',
                      rightPanel === 'story' && 'bg-overlay text-ink',
                    )}
                    title="Story analysis"
                    type="button"
                  >
                    <BookMarked size={18} />
                  </button>
                  <button
                    onClick={() => setRightPanel((p) => (p === 'settings' ? 'none' : 'settings'))}
                    className={cn(
                      'p-2 hover:bg-overlay rounded-full transition-colors',
                      rightPanel === 'settings' && 'bg-overlay text-ink',
                    )}
                    title="Project Settings"
                    type="button"
                  >
                    <SettingsIcon size={18} />
                  </button>
                </>
              )}
            </div>
          </div>
        </header>

        <main
          className={cn(
            'flex-1 w-full mx-auto px-6 py-12 transition-all duration-500',
            isFocusMode ? 'max-w-4xl' : 'max-w-6xl',
          )}
        >
          <div className="flex flex-col">
            <SectionInsertGap
              isFocusMode={isFocusMode}
              label="Add section at top"
              onInsert={() => handleInsertSectionAfter(null)}
            />
            <AnimatePresence mode="popLayout">
              {activeRows.map((section, idx) => (
                <motion.div key={section.id} layout className="flex flex-col">
                  <Section
                    section={section}
                    sectionIndex={idx}
                    sectionCount={activeRows.length}
                    isFocusMode={isFocusMode}
                    onChange={handleChange}
                    onToggleEdit={handleToggleEdit}
                    onSubmit={handleSubmit}
                    onDelete={handleDelete}
                    onMoveSection={handleMoveSection}
                    onSplit={handleSplitSection}
                    onReanalyze={mock ? undefined : handleReanalyzeSection}
                    reanalyzeDisabled={isSubmittingAll || isSaving}
                  />
                  <SectionInsertGap
                    isFocusMode={isFocusMode}
                    onInsert={() => handleInsertSectionAfter(section.id)}
                  />
                </motion.div>
              ))}
            </AnimatePresence>
          </div>
        </main>
      </div>

      <AnimatePresence>
        {rightPanel === 'settings' && !isFocusMode && (
          <SettingsPanel
            isOpen={true}
            metadata={metadata}
            onUpdate={handleMetadataUpdate}
            onClose={() => setRightPanel('none')}
            documentId={metadata.documentId}
            revisionId={metadata.revisionId}
            runId={metadata.runId}
            useMockApi={mock}
            onRestore={handleRestoreBookmark}
            onExportStory={handleExportStoryManuscript}
            runtimeProviders={runtimeProviders}
            runtimeProvidersError={runtimeProvidersError}
          />
        )}
        {rightPanel === 'story' && !isFocusMode && (
          <StoryAnalysisPanel
            isOpen={true}
            onClose={() => setRightPanel('none')}
            title={metadata.title}
            documentId={metadata.documentId}
            revisionId={metadata.revisionId}
            runId={metadata.runId}
            analysisKind={latestAnalysisKind}
            report={latestReport}
            analysisFromFallback={latestAnalysisFromFallback}
            runBoundRevisionId={latestRunRevisionId}
          />
        )}
      </AnimatePresence>

      {submitPhase && (
        <div className="fixed bottom-0 inset-x-0 z-50 flex items-center justify-center gap-4 px-4 py-3 bg-ink/90 text-paper text-sm font-sans shadow-lg border-t border-border/20">
          <Loader2 size={16} className="animate-spin shrink-0" />
          <span className="flex-1 text-center">{submitPhase}</span>
          {!mock && isSubmittingAll && (
            <button
              type="button"
              onClick={() => submitAbortRef.current?.abort()}
              className="shrink-0 px-3 py-1 rounded-lg bg-paper/10 hover:bg-paper/20 text-paper text-xs font-medium"
            >
              Cancel
            </button>
          )}
        </div>
      )}
    </div>
  );
}
