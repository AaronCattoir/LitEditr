import React from 'react';
import { motion } from 'motion/react';
import { X, Download, BookMarked } from 'lucide-react';
import type { ChunkJudgmentEntryPayload, EditorialReportPayload, StoryWidePayload } from '../lib/api';
import {
  buildStoryAnalysisMarkdown,
  defaultStoryAnalysisFilename,
  downloadMarkdownFile,
} from '../lib/analysisExport';

interface StoryAnalysisPanelProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  documentId?: string;
  revisionId?: string;
  runId?: string | null;
  analysisKind?: string | null;
  report: EditorialReportPayload | null;
  /** Report is from document’s latest run, not the current revision (e.g. new save without re-analyze). */
  analysisFromFallback?: boolean;
  runBoundRevisionId?: string | null;
}

function JsonOrText({ value }: { value: unknown }) {
  if (value === null || value === undefined) return <span className="text-ink-light">—</span>;
  if (typeof value === 'string') return <p className="text-sm text-ink-light whitespace-pre-wrap">{value}</p>;
  return (
    <pre className="text-xs font-mono text-ink-light overflow-x-auto p-3 rounded-lg bg-overlay/80 border border-border/60 max-h-48 overflow-y-auto">
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}

function StoryCritiqueSections({ entries }: { entries: ChunkJudgmentEntryPayload[] }) {
  const sorted = [...entries].sort((a, b) => a.position - b.position);
  const visible = sorted.filter((e) => {
    const cr = e.critic_result;
    const dr = e.defense_result;
    const j = e.judgment;
    const hasStructured = Boolean(cr?.critique?.trim() || dr?.defense?.trim());
    const hasJudgment = Boolean(
      (j.guidance && j.guidance.trim()) || (j.core_issue && j.core_issue.trim()),
    );
    return hasStructured || hasJudgment;
  });
  return (
    <section>
      <h3 className="text-xs font-semibold uppercase tracking-wider text-ink-light mb-3">Story critique</h3>
      {visible.length === 0 ? (
        <p className="text-sm text-ink-light leading-relaxed">
          No per-section critique in this report yet. Run Submit All or reanalyze a section.
        </p>
      ) : (
        <div className="flex flex-col gap-5">
          {visible.map((e) => {
          const cr = e.critic_result;
          const dr = e.defense_result;
          const j = e.judgment;
          const hasStructured = Boolean(cr?.critique?.trim() || dr?.defense?.trim());
          const hasJudgment = Boolean(
            (j.guidance && j.guidance.trim()) || (j.core_issue && j.core_issue.trim()),
          );
          return (
            <div
              key={e.chunk_id}
              className="rounded-lg border border-border/70 bg-overlay/40 p-3 text-sm text-ink-light space-y-2"
            >
              <div className="text-xs font-mono text-ink-light/80">Section {e.position + 1}</div>
              {cr?.critique?.trim() ? (
                <div>
                  <span className="text-xs font-semibold uppercase tracking-wide text-ink">Critique</span>
                  <p className="mt-1 whitespace-pre-wrap leading-relaxed">{cr.critique}</p>
                  {cr.failure_points && cr.failure_points.length > 0 && (
                    <ul className="mt-2 list-disc pl-4 text-xs space-y-1">
                      {cr.failure_points.map((fp, i) => (
                        <li key={i}>{fp}</li>
                      ))}
                    </ul>
                  )}
                  {cr.verdict ? <p className="text-xs mt-2 opacity-90">Verdict: {cr.verdict}</p> : null}
                </div>
              ) : null}
              {dr?.defense?.trim() ? (
                <div>
                  <span className="text-xs font-semibold uppercase tracking-wide text-accent">Defense</span>
                  <p className="mt-1 whitespace-pre-wrap leading-relaxed">{dr.defense}</p>
                  {dr.valid_points && dr.valid_points.length > 0 && (
                    <ul className="mt-2 list-disc pl-4 text-xs space-y-1">
                      {dr.valid_points.map((vp, i) => (
                        <li key={i}>{vp}</li>
                      ))}
                    </ul>
                  )}
                </div>
              ) : null}
              {!hasStructured && hasJudgment ? (
                <div>
                  <span className="text-xs font-semibold uppercase tracking-wide text-ink-light">Editorial judgment</span>
                  {j.core_issue ? (
                    <p className="mt-1 text-xs text-ink font-medium">{j.core_issue}</p>
                  ) : null}
                  {j.guidance ? (
                    <p className="mt-1 whitespace-pre-wrap leading-relaxed">{j.guidance}</p>
                  ) : null}
                </div>
              ) : null}
            </div>
          );
          })}
        </div>
      )}
    </section>
  );
}

function StoryWideSections({ sw }: { sw: StoryWidePayload }) {
  return (
    <div className="flex flex-col gap-6">
      <section>
        <h3 className="text-xs font-semibold uppercase tracking-wider text-ink-light mb-2">Plot overview</h3>
        <JsonOrText value={sw.plot_overview} />
      </section>
      <section>
        <h3 className="text-xs font-semibold uppercase tracking-wider text-ink-light mb-2">Character database</h3>
        <JsonOrText value={sw.character_database} />
      </section>
      <section>
        <h3 className="text-xs font-semibold uppercase tracking-wider text-ink-light mb-2">Narrative map</h3>
        <JsonOrText value={sw.narrative_map} />
      </section>
      <section>
        <h3 className="text-xs font-semibold uppercase tracking-wider text-ink-light mb-2">Emotional curve</h3>
        <JsonOrText value={sw.emotional_curve} />
      </section>
      <section>
        <h3 className="text-xs font-semibold uppercase tracking-wider text-ink-light mb-2">Voice baseline</h3>
        <JsonOrText value={sw.voice_baseline} />
      </section>
    </div>
  );
}

export function StoryAnalysisPanel({
  isOpen,
  onClose,
  title,
  documentId,
  revisionId,
  runId,
  analysisKind,
  report,
  analysisFromFallback = false,
  runBoundRevisionId = null,
}: StoryAnalysisPanelProps) {
  if (!isOpen) return null;

  const handleExport = () => {
    const md = buildStoryAnalysisMarkdown({
      title,
      documentId,
      revisionId,
      runId,
      analysisKind,
      report,
    });
    const name = defaultStoryAnalysisFilename({ title, documentId, revisionId });
    downloadMarkdownFile(name, md);
  };

  return (
    <motion.div
      initial={{ x: '100%', opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      exit={{ x: '100%', opacity: 0 }}
      transition={{ type: 'spring', damping: 25, stiffness: 200 }}
      className="fixed right-0 top-0 bottom-0 w-[calc(20rem+10vw)] max-w-[min(32rem,95vw)] bg-surface border-l border-border shadow-2xl z-20 overflow-y-auto font-sans flex flex-col"
    >
      <div className="sticky top-0 bg-surface/90 backdrop-blur-md border-b border-border px-6 py-4 flex items-center justify-between z-10 gap-2">
        <h2 className="font-semibold text-ink text-lg flex items-center gap-2 min-w-0">
          <BookMarked size={18} className="shrink-0 text-accent" />
          <span className="truncate">Story analysis</span>
        </h2>
        <div className="flex items-center gap-1 shrink-0">
          <button
            type="button"
            onClick={handleExport}
            className="p-2 text-ink-light hover:text-accent hover:bg-overlay rounded-full transition-colors"
            title="Export as Markdown"
          >
            <Download size={20} />
          </button>
          <button type="button" onClick={onClose} className="p-2 -mr-2 text-ink-light hover:text-ink hover:bg-overlay rounded-full transition-colors">
            <X size={20} />
          </button>
        </div>
      </div>

      <div className="p-6 flex flex-col gap-6 flex-1">
        {!report ? (
          <p className="text-sm text-ink-light">No analysis loaded for this revision yet. Run Submit All or reanalyze a section.</p>
        ) : (
          <>
            {analysisFromFallback ? (
              <p className="text-xs text-ink-light leading-relaxed rounded-lg border border-accent/25 bg-accent/5 px-3 py-2">
                Showing the latest analysis saved for this document
                {runBoundRevisionId ? (
                  <>
                    {' '}
                    (from revision <span className="font-mono text-[11px]">{runBoundRevisionId.slice(0, 8)}…</span>).
                  </>
                ) : (
                  '.'
                )}{' '}
                Run <span className="font-medium">Submit All</span> to analyze the current revision.
              </p>
            ) : null}
            <div className="text-xs text-ink-light space-y-1 font-mono">
              {(report.run_id || runId) && <div>Run: {report.run_id || runId}</div>}
              {analysisKind && <div>Kind: {analysisKind}</div>}
            </div>

            <div>
              <h3 className="text-xs font-semibold uppercase tracking-wider text-ink-light mb-2">Document summary</h3>
              <p className="text-sm text-ink-light leading-relaxed whitespace-pre-wrap">{report.document_summary}</p>
            </div>

            {report.chunk_judgments?.length ? (
              <StoryCritiqueSections entries={report.chunk_judgments} />
            ) : null}

            {(() => {
              const apiHasStoryWideKey =
                report !== null && Object.prototype.hasOwnProperty.call(report, 'story_wide');
              const sw = report.story_wide;
              if (sw) {
                return <StoryWideSections sw={sw} />;
              }
              if (!apiHasStoryWideKey) {
                return (
                  <p className="text-sm text-ink-light">
                    Story-wide fields are not in the API response. Restart the Python API after updating Editr so{' '}
                    <code className="text-xs bg-overlay px-1 rounded">GET /v1/revisions/…/latest-analysis</code> includes{' '}
                    <code className="text-xs bg-overlay px-1 rounded">story_wide</code>, then refresh this page.
                  </p>
                );
              }
              return (
                <p className="text-sm text-ink-light">
                  No persisted story-wide document state for this run (nothing in{' '}
                  <code className="text-xs bg-overlay px-1 rounded">run_document_state</code> for this run id). Try a full
                  Submit All again; if it persists, check that the API process uses the same database file as the
                  analysis job.
                </p>
              );
            })()}
          </>
        )}
      </div>
    </motion.div>
  );
}
