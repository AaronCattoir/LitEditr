import React, { useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import {
  Sparkles,
  Check,
  Edit2,
  Loader2,
  MessageSquare,
  Trash2,
  ChevronUp,
  ChevronDown,
  RefreshCw,
} from 'lucide-react';
import { cn } from '../lib/utils';
import { SectionData, type GraphChunkJudgment } from '../lib/api';
import { RichTextEditor } from './RichTextEditor';
import { getSceneSplitMarker, splitOnSceneMarkers } from '../lib/manuscriptSerialize';

function hasCriticContent(c: GraphChunkJudgment['critic']): boolean {
  if (!c) return false;
  return Boolean(
    (c.critique && c.critique.trim()) || (c.failure_points && c.failure_points.length > 0),
  );
}

function hasDefenseContent(d: GraphChunkJudgment['defense']): boolean {
  if (!d) return false;
  return Boolean(
    (d.defense && d.defense.trim()) || (d.valid_points && d.valid_points.length > 0),
  );
}

function decisionBadgeClass(decision: string): string {
  const d = decision.toLowerCase();
  if (d === 'keep') return 'bg-emerald-500/15 text-emerald-900 dark:text-emerald-200 border-emerald-500/30';
  if (d === 'rewrite') return 'bg-amber-500/15 text-amber-950 dark:text-amber-100 border-amber-500/35';
  if (d === 'cut') return 'bg-red-500/15 text-red-900 dark:text-red-200 border-red-500/30';
  return 'bg-overlay text-ink border-border';
}

/** Word count from stored section text (markdown/plain); frontend-only, matches typical editor stats. */
function countWords(text: string): number {
  const t = text.trim();
  if (!t) return 0;
  return t.split(/\s+/).filter(Boolean).length;
}

interface SectionProps {
  section: SectionData;
  sectionIndex: number;
  sectionCount: number;
  isFocusMode?: boolean;
  onChange: (id: string, content: string) => void;
  onToggleEdit: (id: string, isEditing: boolean) => void;
  onSubmit: (id: string) => void;
  onDelete: (id: string) => void;
  onMoveSection: (id: string, dir: 'up' | 'down') => void;
  /** Called with the text blocks that should replace this section (split-on-tilde). */
  onSplit: (id: string, parts: string[]) => void;
  /** Re-run pipeline for this chunk only (partial analyze). */
  onReanalyze?: (id: string) => void;
  reanalyzeDisabled?: boolean;
}

export function Section({
  section,
  sectionIndex,
  sectionCount,
  isFocusMode = false,
  onChange,
  onToggleEdit,
  onSubmit,
  onDelete,
  onMoveSection,
  onSplit,
  onReanalyze,
  reanalyzeDisabled = false,
}: SectionProps) {
  const g = section.graphAdvice;
  const [criticOpen, setCriticOpen] = useState(false);
  const [defenseOpen, setDefenseOpen] = useState(false);
  const [judgmentOpen, setJudgmentOpen] = useState(true);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
      onToggleEdit(section.id, false);
    }
  };

  const sceneMarker = getSceneSplitMarker();
  const sceneParts = splitOnSceneMarkers(section.content, sceneMarker);
  const hasSceneLines = sceneParts.length > 1;

  const handleSplitOnMarker = () => {
    if (sceneParts.length > 1) onSplit(section.id, sceneParts);
  };

  const coach = section.quickCoach;
  const legacyFeedback = section.feedback;
  const words = countWords(section.content);

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.95 }}
      className="group relative mb-12 overflow-visible"
    >
      <div
        className={cn(
          'grid items-start gap-8',
          !isFocusMode ? 'grid-cols-1 lg:grid-cols-[minmax(0,1fr)_420px] lg:gap-10' : 'grid-cols-1',
        )}
      >
        <div className="flex flex-col gap-4 w-full min-w-0 overflow-visible pl-10 sm:pl-12">
          <div
            className={cn(
              'relative rounded-2xl transition-all duration-300 overflow-visible',
              section.isEditing ? 'bg-surface shadow-sm ring-1 ring-border p-6' : 'p-2 hover:bg-overlay cursor-pointer',
            )}
            onClick={() => {
              if (!section.isEditing) {
                onToggleEdit(section.id, true);
              }
            }}
          >
            <RichTextEditor
              content={section.content}
              onChange={(content) => onChange(section.id, content)}
              editable={section.isEditing}
              onKeyDown={handleKeyDown}
              onPasteSceneSplit={(parts) => onSplit(section.id, parts)}
            />

            {section.isEditing ? (
              <div className="flex justify-between items-center mt-4 border-t border-border pt-3">
                <span className="text-xs font-sans text-ink-light/60">
                  Press <kbd className="font-mono bg-overlay px-1 rounded">⌘</kbd> +{' '}
                  <kbd className="font-mono bg-overlay px-1 rounded">Enter</kbd> to save
                </span>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    onToggleEdit(section.id, false);
                  }}
                  className="flex items-center gap-2 px-4 py-1.5 rounded-full bg-ink text-paper text-sm font-sans font-medium hover:bg-ink/90 transition-colors"
                  type="button"
                >
                  <Check size={16} />
                  Save Section
                </button>
              </div>
            ) : (
              <div className="absolute -left-4 top-0 -translate-x-full opacity-0 group-hover:opacity-100 transition-opacity flex flex-col gap-2">
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    onToggleEdit(section.id, true);
                  }}
                  className="p-2 rounded-full bg-surface shadow-sm text-ink-light hover:text-ink hover:bg-overlay transition-colors"
                  title="Edit section"
                  type="button"
                >
                  <Edit2 size={16} />
                </button>
                {!isFocusMode && section.content.trim().length > 0 && section.status !== 'submitting' && (
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      onSubmit(section.id);
                    }}
                    className="p-2 rounded-full bg-surface shadow-sm text-accent hover:text-accent-hover hover:bg-overlay transition-colors"
                    title="Quick coach (sparkle)"
                    type="button"
                  >
                    <Sparkles size={16} />
                  </button>
                )}
                {!isFocusMode && onReanalyze && section.content.trim().length > 0 && (
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      onReanalyze(section.id);
                    }}
                    disabled={reanalyzeDisabled || section.status === 'submitting'}
                    className="p-2 rounded-full bg-surface shadow-sm text-ink-light hover:text-accent hover:bg-overlay transition-colors disabled:opacity-30"
                    title="Reanalyze this section (partial analysis)"
                    type="button"
                  >
                    <RefreshCw size={16} />
                  </button>
                )}
                {!isFocusMode && sectionCount > 1 && (
                  <>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        onMoveSection(section.id, 'up');
                      }}
                      disabled={sectionIndex === 0}
                      className="p-2 rounded-full bg-surface shadow-sm text-ink-light hover:text-accent hover:bg-overlay transition-colors disabled:opacity-30"
                      title="Move section up"
                      type="button"
                    >
                      <ChevronUp size={16} />
                    </button>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        onMoveSection(section.id, 'down');
                      }}
                      disabled={sectionIndex >= sectionCount - 1}
                      className="p-2 rounded-full bg-surface shadow-sm text-ink-light hover:text-accent hover:bg-overlay transition-colors disabled:opacity-30"
                      title="Move section down"
                      type="button"
                    >
                      <ChevronDown size={16} />
                    </button>
                  </>
                )}
                {!isFocusMode && hasSceneLines && (
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      handleSplitOnMarker();
                    }}
                    className="p-2 rounded-full bg-surface shadow-sm text-ink-light hover:text-accent hover:bg-overlay transition-colors"
                    title={`Split sections on ${sceneMarker} markers`}
                    type="button"
                  >
                    <span className="font-mono text-sm font-bold leading-none">{sceneMarker}</span>
                  </button>
                )}
                {!isFocusMode && (
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      if (window.confirm('Delete this section?')) onDelete(section.id);
                    }}
                    className="p-2 rounded-full bg-surface shadow-sm text-ink-light hover:text-red-500 hover:bg-overlay transition-colors"
                    title="Delete section"
                    type="button"
                  >
                    <Trash2 size={16} />
                  </button>
                )}
              </div>
            )}

            {!section.isEditing && !section.content && (
              <div className="absolute inset-0 flex items-center p-2 text-ink-light/40 italic font-serif text-lg pointer-events-none">
                Empty section. Click to edit.
              </div>
            )}
          </div>

          <div
            className={cn(
              'flex justify-end px-1',
              section.isEditing ? 'pl-6 pr-6 -mt-1' : 'pl-2 pr-2',
            )}
            role="status"
          >
            <span className="text-xs font-sans text-ink-light/70 tabular-nums select-none">
              {words.toLocaleString()} {words === 1 ? 'word' : 'words'}
            </span>
          </div>

          <AnimatePresence>
            {!isFocusMode &&
              (g ||
                section.status === 'submitting' ||
                (section.status === 'coached' && (coach || legacyFeedback))) && (
                <motion.div
                  initial={{ opacity: 0, height: 0, y: -8 }}
                  animate={{ opacity: 1, height: 'auto', y: 0 }}
                  exit={{ opacity: 0, height: 0 }}
                  className="rounded-2xl border border-border bg-surface/80 shadow-sm p-4 sm:p-5 space-y-3"
                >
                  {(g || section.status === 'submitting') && (
                    <div className="flex items-center gap-2 text-xs font-sans font-semibold text-ink-light uppercase tracking-wider">
                      <Sparkles size={14} className="text-accent shrink-0" />
                      Section summary
                    </div>
                  )}

                  {section.status === 'submitting' && (
                    <div className="flex items-center gap-3 text-sm font-sans text-accent">
                      <Loader2 size={16} className="animate-spin shrink-0" />
                      <span>Quick coach is thinking…</span>
                    </div>
                  )}

                  {g && (
                    <>
                      <div className="flex flex-wrap items-center gap-2">
                        <span
                          className={cn(
                            'inline-flex items-center rounded-full border px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide',
                            decisionBadgeClass(g.decision),
                          )}
                        >
                          {g.decision || '—'}
                        </span>
                        <span className="text-xs font-sans text-ink-light tabular-nums">
                          severity {Number.isFinite(g.severity) ? g.severity.toFixed(2) : '—'}
                        </span>
                      </div>
                      {g.guidance?.trim() ? (
                        <p className="text-sm font-sans text-ink leading-relaxed whitespace-pre-wrap">{g.guidance}</p>
                      ) : null}
                      {g.core_issue?.trim() ? (
                        <p className="text-xs font-sans text-ink-light leading-relaxed">
                          <span className="font-medium text-ink">Core issue:</span> {g.core_issue}
                        </p>
                      ) : null}
                      {(g.emotionalRegister || g.narrativeIntent) && (
                        <div className="flex flex-col gap-3 pt-3 mt-3 border-t border-border/40">
                          {g.emotionalRegister ? (
                            <div>
                              <h4 className="text-[10px] font-sans font-semibold text-ink-light uppercase tracking-wider mb-1">
                                Emotional Register
                              </h4>
                              <p className="text-sm font-sans text-ink leading-relaxed">
                                {g.emotionalRegister}
                              </p>
                            </div>
                          ) : null}
                          {g.narrativeIntent ? (
                            <div>
                              <h4 className="text-[10px] font-sans font-semibold text-ink-light uppercase tracking-wider mb-1">
                                Narrative Intent
                              </h4>
                              <p className="text-sm font-sans text-ink leading-relaxed">
                                {g.narrativeIntent}
                              </p>
                            </div>
                          ) : null}
                        </div>
                      )}
                    </>
                  )}

                  {section.status === 'coached' && (coach || legacyFeedback) && (
                    <div className={cn('flex gap-3', g ? 'pt-2 border-t border-border/60' : '')}>
                      <div className="mt-0.5 text-accent bg-surface p-1.5 rounded-full shadow-sm h-fit shrink-0">
                        <MessageSquare size={16} />
                      </div>
                      <div className="flex-1 min-w-0">
                        <h4 className="text-xs font-sans font-semibold text-accent uppercase tracking-wider mb-1">
                          Quick coach
                        </h4>
                        {coach ? (
                          <>
                            {coach.headline ? (
                              <p className="font-sans text-sm font-medium text-ink mb-2">{coach.headline}</p>
                            ) : null}
                            {coach.bullets?.length ? (
                              <ul className="list-disc pl-4 space-y-1 text-sm text-ink-light">
                                {coach.bullets.map((b, i) => (
                                  <li key={i}>{b}</li>
                                ))}
                              </ul>
                            ) : null}
                            {coach.try_next ? (
                              <p className="mt-2 text-sm text-ink-light">
                                <span className="font-medium text-ink">Try next:</span> {coach.try_next}
                              </p>
                            ) : null}
                          </>
                        ) : (
                          <p className="font-sans text-sm text-ink-light leading-relaxed">{legacyFeedback}</p>
                        )}
                      </div>
                    </div>
                  )}
                </motion.div>
              )}
          </AnimatePresence>
        </div>

        {!isFocusMode && (
          <div className="relative h-full hidden lg:block">
            <AnimatePresence>
              {g && (
                <motion.div
                  initial={{ opacity: 0, x: 20 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: 20 }}
                  className="flex flex-col gap-2 bg-accent/5 p-4 rounded-2xl border border-accent/10 shadow-sm"
                >
                  <div className="flex items-center gap-2 text-accent font-sans font-semibold text-xs uppercase tracking-wider shrink-0">
                    <Sparkles size={14} />
                    Graph analysis
                  </div>

                  {hasCriticContent(g.critic) && (
                    <div className="rounded-xl border border-border/50 bg-surface/60 overflow-hidden">
                      <button
                        type="button"
                        onClick={() => setCriticOpen(!criticOpen)}
                        className="w-full flex items-center justify-between gap-2 px-3 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-ink hover:bg-overlay/60 transition-colors"
                      >
                        Critic
                        <ChevronDown
                          className={cn('h-4 w-4 shrink-0 text-ink-light transition-transform', criticOpen && 'rotate-180')}
                        />
                      </button>
                      {criticOpen && g.critic && (
                        <div className="px-3 pb-3 pt-0 border-t border-border/40 space-y-2">
                          {g.critic.verdict ? (
                            <p className="text-[10px] uppercase tracking-wider text-ink-light">
                              Verdict: <span className="text-ink font-medium">{g.critic.verdict}</span>
                            </p>
                          ) : null}
                          {g.critic.critique ? (
                            <p className="text-sm font-sans text-ink-light leading-relaxed whitespace-pre-wrap">
                              {g.critic.critique}
                            </p>
                          ) : null}
                          {g.critic.failure_points && g.critic.failure_points.length > 0 ? (
                            <ul className="list-disc pl-4 space-y-1 text-xs text-ink-light">
                              {g.critic.failure_points.map((fp, i) => (
                                <li key={i}>{fp}</li>
                              ))}
                            </ul>
                          ) : null}
                        </div>
                      )}
                    </div>
                  )}

                  {hasDefenseContent(g.defense) && (
                    <div className="rounded-xl border border-border/50 bg-surface/60 overflow-hidden">
                      <button
                        type="button"
                        onClick={() => setDefenseOpen(!defenseOpen)}
                        className="w-full flex items-center justify-between gap-2 px-3 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-ink hover:bg-overlay/60 transition-colors"
                      >
                        Advocate
                        <ChevronDown
                          className={cn('h-4 w-4 shrink-0 text-ink-light transition-transform', defenseOpen && 'rotate-180')}
                        />
                      </button>
                      {defenseOpen && g.defense && (
                        <div className="px-3 pb-3 pt-0 border-t border-border/40 space-y-2">
                          {g.defense.salvageability ? (
                            <p className="text-[10px] uppercase tracking-wider text-ink-light">
                              Salvageability:{' '}
                              <span className="text-ink font-medium">{g.defense.salvageability}</span>
                            </p>
                          ) : null}
                          {g.defense.defense ? (
                            <p className="text-sm font-sans text-ink-light leading-relaxed whitespace-pre-wrap">
                              {g.defense.defense}
                            </p>
                          ) : null}
                          {g.defense.valid_points && g.defense.valid_points.length > 0 ? (
                            <ul className="list-disc pl-4 space-y-1 text-xs text-ink-light">
                              {g.defense.valid_points.map((vp, i) => (
                                <li key={i}>{vp}</li>
                              ))}
                            </ul>
                          ) : null}
                        </div>
                      )}
                    </div>
                  )}

                  <div className="rounded-xl border border-accent/20 bg-surface/80 overflow-hidden">
                    <button
                      type="button"
                      onClick={() => setJudgmentOpen(!judgmentOpen)}
                      className="w-full flex items-center justify-between gap-2 px-3 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-accent hover:bg-accent/5 transition-colors"
                    >
                      Judgment
                      <ChevronDown
                        className={cn('h-4 w-4 shrink-0 text-ink-light transition-transform', judgmentOpen && 'rotate-180')}
                      />
                    </button>
                    {judgmentOpen && (
                      <div className="px-3 pb-3 pt-0 border-t border-border/40 space-y-2">
                        <p className="text-sm font-sans text-ink leading-relaxed">{g.guidance}</p>
                        {g.reasoning ? (
                          <p className="text-xs font-sans text-ink-light leading-relaxed whitespace-pre-wrap">
                            <span className="font-medium text-ink">Reasoning:</span> {g.reasoning}
                          </p>
                        ) : null}
                        {g.core_issue ? (
                          <p className="text-xs font-sans text-ink-light">
                            <span className="font-medium text-ink">Core issue:</span> {g.core_issue}
                          </p>
                        ) : null}
                        <p className="text-xs font-sans text-ink-light">
                          {g.decision} · severity {g.severity.toFixed(2)}
                        </p>
                      </div>
                    )}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        )}
      </div>
    </motion.div>
  );
}
