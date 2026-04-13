/**
 * LitEditr API client: documents, chapters, revisions, analyze (async job), quick-coach, bookmarks.
 * Set VITE_USE_MOCK_API=true to use local delays + mock copy (no backend).
 */

// --- Types ---

/** LLM backend for analysis / quick coach (matches server `Literal["openai", "gemini"]`). */
export type BetaLlmProviderId = 'openai' | 'gemini';

/** Mirrors backend `GenreIntention` (latest-analysis report + analyze bodies). */
export interface GenreIntentionPayload {
  genre: string;
  subgenre_tags: string[];
  tone_descriptors: string[];
  reference_authors: string[];
  short_story_single_chapter?: boolean;
}

export interface ProjectMetadata {
  title: string;
  chapter: string;
  genre: string;
  scene: string;
  characters: string[];
  /** Style targets (comma-edited in Settings); sent as `subgenre_tags` on analyze / quick-coach. */
  subgenreTags?: string[];
  toneDescriptors?: string[];
  referenceAuthors?: string[];
  plot?: string;
  documentId?: string;
  revisionId?: string;
  runId?: string;
  /** Revision id of the last full or partial analysis job (for “saved vs analyzed” UI). */
  analyzedRevisionId?: string;
  /** Single-chapter short story: analysis prompts skip novel-style multi-chapter expectations. */
  shortStorySingleChapter?: boolean;
  /** Selected beta LLM provider for runs (server keys from env; not stored as secrets here). */
  llmProvider?: BetaLlmProviderId;
}

/** Character offsets into full manuscript (Unicode code points); matches backend EvidenceSpan. */
export interface EvidenceSpanPayload {
  start_char: number;
  end_char: number;
  quote?: string;
  label?: string;
}

/** Serialized critic layer (matches backend CriticResult). */
export interface GraphCriticPayload {
  critique: string;
  failure_points?: string[];
  verdict?: string;
  evidence_spans?: EvidenceSpanPayload[];
}

/** Serialized defense / advocate layer (matches backend DefenseResult). */
export interface GraphDefensePayload {
  defense: string;
  valid_points?: string[];
  salvageability?: string;
  evidence_spans?: EvidenceSpanPayload[];
}

export interface GraphChunkJudgment {
  guidance: string;
  core_issue: string;
  decision: string;
  severity: number;
  reasoning?: string;
  critic?: GraphCriticPayload | null;
  defense?: GraphDefensePayload | null;
  /** Editor judgment evidence spans (matches backend EditorJudgment.evidence_spans). */
  judgment_evidence_spans?: EvidenceSpanPayload[];
  /** Synthesized spans mapped to specific text with critic/advocate blurbs */
  synthesis_spans?: SpanSynthesisPayload[];
  /** From story_wide.emotional_curve for this chunk_id (last entry wins). */
  emotionalRegister?: string;
  /** From story_wide.narrative_map for this chunk_id (last entry wins). */
  narrativeIntent?: string;
}

export interface QuickCoachAdvice {
  headline: string;
  bullets: string[];
  try_next?: string | null;
}

export interface SectionData {
  id: string;
  content: string;
  isEditing: boolean;
  status: 'draft' | 'submitting' | 'coached';
  /** Sparkle quick-coach structured response */
  quickCoach?: QuickCoachAdvice | null;
  /** Graph column: from EditorialReportChunkJudgment after Submit All */
  graphAdvice?: GraphChunkJudgment | null;
  /** Legacy: single string when using mock */
  feedback?: string;
}

export interface ChapterDoc {
  id: string;
  title: string;
  sortOrder: number;
  rows: SectionData[];
}

export interface ProjectBootstrap {
  metadata: ProjectMetadata;
  chapters: ChapterDoc[];
  /** When restoring a saved draft, select this chapter tab. */
  activeChapterId?: string;
}

export interface ClientChunkSpan {
  chunk_id: string;
  start_char: number;
  end_char: number;
}

export interface ApiChapterRow {
  chapter_id: string;
  document_id: string;
  title: string;
  sort_order: number;
  created_at: string;
}

export interface AnalyzeQueuedResponse {
  job_id: string;
  status: string;
  reason?: string;
}

export interface JobRecord {
  job_id: string;
  kind: string;
  status: string;
  document_id: string | null;
  revision_id: string | null;
  run_id: string | null;
  result: AnalyzeJobResult | null;
  error: string | null;
}

export interface JobProgressResponse {
  job_id: string;
  status: string;
  run_id: string | null;
  revision_id: string | null;
  document_id: string | null;
  completed_chunks: number;
  total_chunks: number | null;
  report: EditorialReportPayload | null;
  error: string | null;
}

export interface AnalyzeJobResult {
  run_id: string;
  document_id: string;
  revision_id: string;
  report: EditorialReportPayload;
  analysis_kind?: string | null;
}

export interface LatestRevisionAnalysisResponse {
  revision_id: string;
  run_id: string | null;
  analysis_kind?: string | null;
  report: EditorialReportPayload | null;
  /** True when report is from the latest run on the document, not this exact revision (e.g. after Save). */
  from_fallback?: boolean;
  /** Revision id the run was recorded against (may differ from `revision_id` when from_fallback). */
  run_revision_id?: string | null;
}

/** Story-wide fields from persisted run_document_state (latest-analysis). */
export interface StoryWidePayload {
  plot_overview: Record<string, unknown> | null;
  character_database: Record<string, unknown> | null;
  narrative_map: unknown[];
  emotional_curve: unknown[];
  voice_baseline: Record<string, unknown> | null;
}

export interface RevisionChunkRow {
  chunk_id: string;
  position: number;
  start_char: number;
  end_char: number;
}

export interface EditorialReportPayload {
  run_id: string;
  document_summary: string;
  chunk_judgments: ChunkJudgmentEntryPayload[];
  story_wide?: StoryWidePayload | null;
  genre_intention?: GenreIntentionPayload | null;
}

export interface SpanSynthesisPayload {
  quote: string;
  critic_blurb: string;
  advocate_blurb: string;
  start_char: number;
  end_char: number;
}

export interface EvidenceSynthesisResultPayload {
  spans: SpanSynthesisPayload[];
}

export interface ChunkJudgmentEntryPayload {
  chunk_id: string;
  position: number;
  judgment: {
    decision: string;
    severity: number;
    guidance: string;
    core_issue: string;
    reasoning?: string;
    evidence_spans?: EvidenceSpanPayload[];
  };
  critic_result?: GraphCriticPayload | null;
  defense_result?: GraphDefensePayload | null;
  evidence_synthesis?: EvidenceSynthesisResultPayload | null;
}

export interface BookmarkRow {
  id: number;
  document_id: string;
  label: string;
  revision_id: string;
  run_id: string | null;
  metadata?: Record<string, unknown>;
  created_at?: string;
}

export interface RestorePayload {
  bookmark: BookmarkRow & { metadata?: Record<string, unknown> };
  revision: { revision_id: string; full_text: string; document_id: string };
  run: Record<string, unknown> | null;
}

/** Parsed from persona `llm_snapshot.visual_model` for generative Inkblot SVG. */
export interface InkblotVisualState {
  svg_path_d: string;
  primary_color: string;
  secondary_color: string;
  animation_speed: number;
}

/** Extract visual fields from stored llm_snapshot JSON (snake_case from backend). */
export function parseInkblotVisualFromLlmSnapshot(
  llm: Record<string, unknown> | null | undefined,
): InkblotVisualState | null {
  if (!llm || typeof llm !== 'object') return null;
  const vm = llm.visual_model;
  if (!vm || typeof vm !== 'object') return null;
  const o = vm as Record<string, unknown>;
  const d = typeof o.svg_path_d === 'string' ? o.svg_path_d.trim() : '';
  const primary = typeof o.primary_color === 'string' ? o.primary_color.trim() : '';
  const secondary = typeof o.secondary_color === 'string' ? o.secondary_color.trim() : '';
  const speed = typeof o.animation_speed === 'number' && Number.isFinite(o.animation_speed) ? o.animation_speed : 1;
  if (!d || d.length < 8) return null;
  return {
    svg_path_d: d,
    primary_color: /^#[0-9A-Fa-f]{6}$/.test(primary) ? primary : '#6B5B6B',
    secondary_color: /^#[0-9A-Fa-f]{6}$/.test(secondary) ? secondary : '#C4A8B8',
    animation_speed: Math.min(3, Math.max(0.25, speed)),
  };
}

/** Inkblot story persona (GET /v1/documents/{id}/persona). */
export interface StoryPersonaSnapshotPayload {
  version: number;
  state: string;
  deterministic: Record<string, unknown>;
  /** May include `visual_model` when persona refresh produced generative SVG hints. */
  llm_snapshot: Record<string, unknown> | null;
  pet_style_policy: Record<string, unknown> | null;
  source_run_id: string | null;
  created_at?: string;
}

export interface StoryPersonaApiResponse {
  document_id: string;
  snapshot: StoryPersonaSnapshotPayload | null;
  soul_loaded: boolean;
  soul_paths: string[];
  persona_refresh_pending: boolean;
  latest_run_id: string | null;
  inkblot_memory?: Record<string, unknown> | null;
  inkblot_memory_updated_at?: string | null;
}

export interface StoryChatRequestBody {
  revision_id?: string | null;
  user_message: string;
  chunk_ids?: string[] | null;
  chapter_id?: string | null;
  max_words?: number;
  session_id?: string | null;
  provider?: BetaLlmProviderId | null;
}

export interface StoryChatResponsePayload {
  answer: string;
  used_persona_version: number | null;
  session_id: string;
  context_manifest: Record<string, unknown>;
  truncation_notice?: string | null;
  confidence?: number | null;
  persona_refresh_pending: boolean;
  inkblot_memory_updated_at?: string | null;
  success: boolean;
  error?: string | null;
  error_code?: string | null;
  recovery_hints?: string[];
}

// --- Config ---

export function useMockApi(): boolean {
  return import.meta.env.VITE_USE_MOCK_API === 'true';
}

export function apiUrl(path: string): string {
  const base = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '');
  if (!base) return path;
  return `${base}${path.startsWith('/') ? path : `/${path}`}`;
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const url = apiUrl(path);
  const headers: HeadersInit = {
    'Content-Type': 'application/json',
    ...(init?.headers as Record<string, string>),
  };
  const res = await fetch(url, { ...init, headers });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`HTTP ${res.status}: ${text}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export function normalizeGenreForApi(g: string): string {
  const t = g.trim().toLowerCase().replace(/\s+/g, '_');
  return t || 'literary_fiction';
}

function trimNonEmptyStrings(arr: string[] | undefined): string[] {
  return (arr ?? []).map((s) => s.trim()).filter(Boolean);
}

/** Build analyze / quick-coach genre-intention fields from project metadata (not scene). */
export function genreIntentionPayloadFromMetadata(
  m: ProjectMetadata,
): Pick<GenreIntentionPayload, 'genre' | 'subgenre_tags' | 'tone_descriptors' | 'reference_authors'> {
  return {
    genre: normalizeGenreForApi(m.genre),
    subgenre_tags: trimNonEmptyStrings(m.subgenreTags),
    tone_descriptors: trimNonEmptyStrings(m.toneDescriptors),
    reference_authors: trimNonEmptyStrings(m.referenceAuthors),
  };
}

// --- REST ---

export interface DocumentListRow {
  document_id: string;
  title: string;
  author: string;
  created_at: string;
}

export async function listDocuments(limit = 100): Promise<{ documents: DocumentListRow[] }> {
  return apiFetch(`/v1/documents?limit=${limit}`);
}

export async function createDocument(body: { title?: string; author?: string }): Promise<{ document_id: string }> {
  const params = new URLSearchParams();
  if (body.title != null && body.title !== '') params.set('title', body.title);
  if (body.author != null && body.author !== '') params.set('author', body.author);
  const q = params.toString();
  return apiFetch(`/v1/documents${q ? `?${q}` : ''}`, { method: 'POST' });
}

export async function deleteDocument(documentId: string): Promise<{ deleted: boolean; document_id: string }> {
  return apiFetch(`/v1/documents/${encodeURIComponent(documentId)}`, { method: 'DELETE' });
}

export async function listDocumentChapters(documentId: string): Promise<{ document_id: string; chapters: ApiChapterRow[] }> {
  return apiFetch(`/v1/documents/${encodeURIComponent(documentId)}/chapters`);
}

export async function createDocumentChapter(
  documentId: string,
  body: { title: string; sort_order?: number },
): Promise<{ chapter_id: string; document_id: string }> {
  return apiFetch(`/v1/documents/${encodeURIComponent(documentId)}/chapters`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export async function updateDocumentChapter(
  chapterId: string,
  body: { title?: string; sort_order?: number },
): Promise<{ updated: boolean; chapter_id: string }> {
  return apiFetch(`/v1/chapters/${encodeURIComponent(chapterId)}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  });
}

export async function deleteDocumentChapter(chapterId: string): Promise<{ deleted: boolean }> {
  return apiFetch(`/v1/chapters/${encodeURIComponent(chapterId)}`, { method: 'DELETE' });
}

export async function getDocumentManuscript(documentId: string): Promise<{
  document_id: string;
  chapters: ApiChapterRow[];
  current_revision: { revision_id: string; full_text: string } | null;
}> {
  return apiFetch(`/v1/documents/${encodeURIComponent(documentId)}/manuscript`);
}

export async function createRevision(
  documentId: string,
  body: {
    text: string;
    parent_revision_id?: string | null;
    /** When set, server persists chunk_versions for this revision (story chat, quick coach, list chunks). */
    chunks?: ClientChunkSpan[];
    /** Optional save origin metadata for lightweight revision-event tagging. */
    save_source?: 'toolbar' | 'section_save';
    save_section_id?: string | null;
  },
): Promise<{ revision_id: string; document_id: string }> {
  return apiFetch(`/v1/documents/${encodeURIComponent(documentId)}/revisions`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

/** Body for POST `/v1/revisions/{id}/analyze` (subset enforced by server). */
export interface AnalyzeRevisionBody {
  genre: string;
  subgenre_tags: string[];
  tone_descriptors: string[];
  reference_authors: string[];
  title?: string | null;
  chunks: ClientChunkSpan[];
  short_story_single_chapter?: boolean;
  base_run_id?: string;
  only_chunk_ids?: string[];
  provider?: BetaLlmProviderId | null;
}

/** Body for POST `/v1/revisions/{id}/quick-coach`. */
export interface QuickCoachRequestBody {
  chunk_id: string;
  run_id?: string | null;
  focus?: string | null;
  genre?: string | null;
  subgenre_tags: string[];
  tone_descriptors: string[];
  reference_authors: string[];
  title?: string | null;
  chunks?: ClientChunkSpan[];
  current_chunk_text?: string;
  short_story_single_chapter?: boolean;
  provider?: BetaLlmProviderId | null;
  /** When true, server appends user+assistant turns to Inkblot story chat. */
  append_story_chat?: boolean;
  story_chat_session_id?: string | null;
}

export interface RuntimeProviderModels {
  default: string;
  fast: string;
  pro: string;
}

export interface RuntimeProviderEntry {
  id: BetaLlmProviderId;
  configured: boolean;
  models: RuntimeProviderModels;
}

export interface RuntimeProvidersResponse {
  default_provider: BetaLlmProviderId;
  providers: RuntimeProviderEntry[];
}

export async function getRuntimeProviders(): Promise<RuntimeProvidersResponse> {
  return apiFetch('/v1/runtime/providers');
}

export function isProviderConfigured(
  snapshot: RuntimeProvidersResponse,
  id: BetaLlmProviderId,
): boolean {
  return snapshot.providers.find((p) => p.id === id)?.configured ?? false;
}

/** Prefer saved choice if still configured; else server default if configured; else first configured provider. */
export function resolveSelectableLlmProvider(
  snapshot: RuntimeProvidersResponse,
  preferred?: BetaLlmProviderId | null,
): BetaLlmProviderId | null {
  if (preferred && isProviderConfigured(snapshot, preferred)) return preferred;
  if (isProviderConfigured(snapshot, snapshot.default_provider)) return snapshot.default_provider;
  for (const p of snapshot.providers) {
    if (p.configured) return p.id;
  }
  return null;
}

export async function postAnalyzeRevision(
  revisionId: string,
  body: AnalyzeRevisionBody,
): Promise<AnalyzeQueuedResponse> {
  const url = apiUrl(`/v1/revisions/${encodeURIComponent(revisionId)}/analyze`);
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (res.status === 202) {
    return (await res.json()) as AnalyzeQueuedResponse;
  }
  const text = await res.text();
  throw new Error(`analyze ${res.status}: ${text}`);
}

export async function getJob(jobId: string): Promise<JobRecord> {
  return apiFetch(`/v1/jobs/${encodeURIComponent(jobId)}`);
}

export async function getJobProgress(jobId: string): Promise<JobProgressResponse> {
  return apiFetch(`/v1/jobs/${encodeURIComponent(jobId)}/progress`);
}

export async function getLatestRevisionAnalysis(
  revisionId: string,
): Promise<LatestRevisionAnalysisResponse> {
  return apiFetch(`/v1/revisions/${encodeURIComponent(revisionId)}/latest-analysis`);
}

export async function listRevisionChunks(
  revisionId: string,
): Promise<{ revision_id: string; chunks: RevisionChunkRow[] }> {
  return apiFetch(`/v1/revisions/${encodeURIComponent(revisionId)}/chunks`);
}

export async function listDocumentBookmarks(documentId: string): Promise<{ document_id: string; bookmarks: BookmarkRow[] }> {
  return apiFetch(`/v1/documents/${encodeURIComponent(documentId)}/bookmarks`);
}

export async function createBookmark(
  documentId: string,
  body: { label: string; revision_id: string; run_id?: string | null; metadata?: Record<string, unknown> },
): Promise<{ bookmark_id: number }> {
  return apiFetch(`/v1/documents/${encodeURIComponent(documentId)}/bookmarks`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export async function restoreBookmark(bookmarkId: number): Promise<RestorePayload> {
  return apiFetch(`/v1/bookmarks/${bookmarkId}/restore`);
}

export async function getStoryPersona(documentId: string): Promise<StoryPersonaApiResponse> {
  return apiFetch(`/v1/documents/${encodeURIComponent(documentId)}/persona`);
}

export async function postStoryChat(
  documentId: string,
  body: StoryChatRequestBody,
): Promise<StoryChatResponsePayload> {
  return apiFetch(`/v1/documents/${encodeURIComponent(documentId)}/story-chat`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export async function listStoryChatSessions(
  documentId: string,
): Promise<{ document_id: string; sessions: Record<string, unknown>[] }> {
  return apiFetch(`/v1/documents/${encodeURIComponent(documentId)}/story-chat/sessions`);
}

export async function listStoryChatTurns(sessionId: string): Promise<{ session_id: string; turns: Record<string, unknown>[] }> {
  return apiFetch(`/v1/story-chat/sessions/${encodeURIComponent(sessionId)}/turns`);
}

/** Enqueue full-session memory extraction when the user closes the Inkblot panel. */
export async function postStoryChatSessionClose(
  documentId: string,
  sessionId: string,
  body?: { provider?: BetaLlmProviderId | null; last_turn_index?: number | null },
): Promise<{ success: boolean; scheduled: boolean; error?: string | null }> {
  return apiFetch(
    `/v1/documents/${encodeURIComponent(documentId)}/story-chat/sessions/${encodeURIComponent(sessionId)}/close-summary`,
    { method: 'POST', body: JSON.stringify(body ?? {}) },
  );
}

export interface QuickCoachOobPayload {
  error?: string;
  error_code?: string;
  requires_reanalysis?: boolean;
  delta_chars?: number;
  threshold_chars?: number;
  analyzed_char_len?: number;
  current_char_len?: number;
  run_id?: string | null;
  revision_id?: string | null;
}

export type QuickCoachResult =
  | {
      kind: 'advice';
      advice: QuickCoachAdvice;
      run_id?: string | null;
      revision_id?: string | null;
      story_chat_session_id?: string | null;
      story_chat_appended?: boolean;
    }
  | { kind: 'queued'; job_id: string; status: string; reason?: string }
  | ({ kind: 'oob' } & QuickCoachOobPayload)
  | { kind: 'run_revision_mismatch'; error?: string };

export async function postQuickCoach(
  revisionId: string,
  body: QuickCoachRequestBody,
): Promise<QuickCoachResult> {
  const url = apiUrl(`/v1/revisions/${encodeURIComponent(revisionId)}/quick-coach`);
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const data = (await res.json()) as Record<string, unknown>;
  if (res.status === 202) {
    return {
      kind: 'queued',
      job_id: String(data.job_id ?? ''),
      status: String(data.status ?? 'queued'),
      reason: data.reason as string | undefined,
    };
  }
  if (res.status === 200) {
    const advice = data.advice as QuickCoachAdvice | null | undefined;
    const sid = data.story_chat_session_id;
    return {
      kind: 'advice',
      advice: advice ?? { headline: '', bullets: [] },
      run_id: data.run_id as string | null | undefined,
      revision_id: data.revision_id as string | null | undefined,
      story_chat_session_id: typeof sid === 'string' && sid ? sid : null,
      story_chat_appended: Boolean(data.story_chat_appended),
    };
  }
  if (res.status === 422) {
    const detail = data.detail;
    if (typeof detail === 'string' && detail.includes('run_id does not belong to this revision')) {
      return { kind: 'run_revision_mismatch', error: detail };
    }
    if (detail && typeof detail === 'object' && !Array.isArray(detail)) {
      const d = detail as Record<string, unknown>;
      if (d.error_code === 'quick_coach_oob') {
        return {
          kind: 'oob',
          error: typeof d.error === 'string' ? d.error : undefined,
          error_code: 'quick_coach_oob',
          requires_reanalysis: Boolean(d.requires_reanalysis),
          delta_chars: typeof d.delta_chars === 'number' ? d.delta_chars : undefined,
          threshold_chars: typeof d.threshold_chars === 'number' ? d.threshold_chars : undefined,
          analyzed_char_len: typeof d.analyzed_char_len === 'number' ? d.analyzed_char_len : undefined,
          current_char_len: typeof d.current_char_len === 'number' ? d.current_char_len : undefined,
          run_id: (d.run_id as string | null | undefined) ?? null,
          revision_id: (d.revision_id as string | null | undefined) ?? null,
        };
      }
      const msg = typeof d.msg === 'string' ? d.msg : typeof d.message === 'string' ? d.message : '';
      if (msg.includes('run_id does not belong to this revision')) {
        return { kind: 'run_revision_mismatch', error: msg };
      }
    }
    if (Array.isArray(detail)) {
      for (const item of detail) {
        if (item && typeof item === 'object') {
          const msg = String((item as Record<string, unknown>).msg ?? '');
          if (msg.includes('run_id does not belong to this revision')) {
            return { kind: 'run_revision_mismatch', error: msg };
          }
        }
      }
    }
  }
  const detail = (data.detail as string) || JSON.stringify(data);
  throw new Error(`quick-coach ${res.status}: ${detail}`);
}

export function mapEvidenceSpans(raw: unknown): EvidenceSpanPayload[] {
  if (!Array.isArray(raw)) return [];
  const out: EvidenceSpanPayload[] = [];
  for (const item of raw) {
    if (!item || typeof item !== 'object') continue;
    const o = item as Record<string, unknown>;
    const s = o.start_char;
    const e = o.end_char;
    if (typeof s !== 'number' || typeof e !== 'number' || e <= s) continue;
    out.push({
      start_char: s,
      end_char: e,
      quote: typeof o.quote === 'string' ? o.quote : '',
      label: typeof o.label === 'string' ? o.label : 'evidence',
    });
  }
  return out;
}

function mapCritic(raw: unknown): GraphCriticPayload | null {
  if (!raw || typeof raw !== 'object') return null;
  const o = raw as Record<string, unknown>;
  const spans = mapEvidenceSpans(o.evidence_spans);
  return {
    critique: typeof o.critique === 'string' ? o.critique : '',
    failure_points: Array.isArray(o.failure_points) ? o.failure_points.map(String) : [],
    verdict: typeof o.verdict === 'string' ? o.verdict : undefined,
    ...(spans.length ? { evidence_spans: spans } : {}),
  };
}

function mapDefense(raw: unknown): GraphDefensePayload | null {
  if (!raw || typeof raw !== 'object') return null;
  const o = raw as Record<string, unknown>;
  const spans = mapEvidenceSpans(o.evidence_spans);
  return {
    defense: typeof o.defense === 'string' ? o.defense : '',
    valid_points: Array.isArray(o.valid_points) ? o.valid_points.map(String) : [],
    salvageability: typeof o.salvageability === 'string' ? o.salvageability : undefined,
    ...(spans.length ? { evidence_spans: spans } : {}),
  };
}

export function judgmentFromPayload(entry: ChunkJudgmentEntryPayload | undefined): GraphChunkJudgment | null {
  if (!entry?.judgment) return null;
  const j = entry.judgment;
  const jSpans = mapEvidenceSpans(j.evidence_spans);
  const synthSpans = entry.evidence_synthesis?.spans ?? [];
  return {
    guidance: j.guidance ?? '',
    core_issue: j.core_issue ?? '',
    decision: j.decision ?? '',
    severity: typeof j.severity === 'number' ? j.severity : 0,
    reasoning: typeof j.reasoning === 'string' ? j.reasoning : '',
    critic: mapCritic(entry.critic_result),
    defense: mapDefense(entry.defense_result),
    ...(jSpans.length ? { judgment_evidence_spans: jSpans } : {}),
    ...(synthSpans.length ? { synthesis_spans: synthSpans } : {}),
  };
}

/** Last matching row wins (same semantics as backend document_state upsert per chunk_id). */
function storyWideValueByChunkId(
  rows: unknown[] | undefined,
  chunkId: string,
  valueKey: string,
): string | undefined {
  if (!Array.isArray(rows)) return undefined;
  let last: string | undefined;
  for (const row of rows) {
    if (!row || typeof row !== 'object') continue;
    const o = row as Record<string, unknown>;
    if (String(o.chunk_id ?? '') !== chunkId) continue;
    const v = o[valueKey];
    if (typeof v === 'string' && v.trim()) last = v.trim();
  }
  return last;
}

export function buildJudgmentMap(report: EditorialReportPayload | undefined): Map<string, GraphChunkJudgment> {
  const m = new Map<string, GraphChunkJudgment>();
  if (!report?.chunk_judgments) return m;
  for (const cj of report.chunk_judgments) {
    const g = judgmentFromPayload(cj);
    if (g) m.set(cj.chunk_id, g);
  }
  const ec = report.story_wide?.emotional_curve;
  const nm = report.story_wide?.narrative_map;
  for (const [chunkId, g] of m) {
    const emotionalRegister = storyWideValueByChunkId(ec, chunkId, 'register');
    const narrativeIntent = storyWideValueByChunkId(nm, chunkId, 'intent');
    if (emotionalRegister || narrativeIntent) {
      m.set(chunkId, {
        ...g,
        ...(emotionalRegister ? { emotionalRegister } : {}),
        ...(narrativeIntent ? { narrativeIntent } : {}),
      });
    }
  }
  return m;
}

export async function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

export async function pollJobUntilDone(
  jobId: string,
  opts?: {
    intervalMs?: number;
    maxAttempts?: number;
    signal?: AbortSignal;
    onTick?: (job: JobRecord, attempt: number) => void | Promise<void>;
  },
): Promise<JobRecord> {
  const interval = opts?.intervalMs ?? 2000;
  // Default to 60 minutes for long-running full-manuscript analyses.
  const max = opts?.maxAttempts ?? 1800;
  const signal = opts?.signal;
  for (let i = 0; i < max; i++) {
    if (signal?.aborted) {
      const err = new Error('Aborted');
      err.name = 'AbortError';
      throw err;
    }
    const j = await getJob(jobId);
    if (opts?.onTick) await opts.onTick(j, i);
    if (j.status === 'succeeded') return j;
    if (j.status === 'failed') throw new Error(j.error || 'job failed');
    await sleep(interval);
  }
  throw new Error('job polling timed out');
}

// --- Mock (legacy) ---

export const MOCK_COACHING_RESPONSES = [
  "This is a strong start! Consider expanding on the emotional 'why' behind this thought to connect more deeply with the reader.",
  'Great clarity here. You might want to break this into two shorter sentences for more impact.',
  'I love the tone of this section. To make it even cozier, try adding a sensory detail (what did it look, sound, or feel like?).',
  'This point is crucial. Could you provide a brief, concrete example to anchor the concept for your audience?',
  "You're building good momentum. Make sure the transition to the next paragraph feels seamless by hinting at what's coming.",
];

export const MOCK_GRAPH_ADVICE: GraphChunkJudgment = {
  guidance:
    'The pacing here feels a bit rushed compared to the previous section. Consider slowing down to let the reader absorb the atmosphere.',
  core_issue: 'Pacing vs. prior section',
  decision: 'keep',
  severity: 0.35,
  reasoning: 'The scene earns its beat structurally; line-level polish only.',
  critic: {
    critique:
      'PROSE-CRAFT: A few sentences stack similar rhythms. NARRATIVE ARCHITECTURE: The turn lands but could use one more beat of pressure before release.',
    failure_points: ['Rhythm clustering in mid-paragraph', 'Slight undersell of the reveal'],
    verdict: 'borderline',
  },
  defense: {
    defense:
      'The rhythm clustering mirrors the narrator’s anxiety; the “undersold” moment reads as restraint, not accident, given genre.',
    valid_points: ['Voice-consistent hesitation', 'Scene still advances stakes'],
    salvageability: 'high',
  },
};

export async function submitToLanggraphMock(content: string): Promise<string> {
  void content;
  return new Promise((resolve) => {
    setTimeout(() => {
      const randomFeedback = MOCK_COACHING_RESPONSES[Math.floor(Math.random() * MOCK_COACHING_RESPONSES.length)];
      resolve(randomFeedback);
    }, 1500 + Math.random() * 1000);
  });
}

export async function submitAllToLanggraphMock(
  sections: SectionData[],
  metadata: ProjectMetadata,
): Promise<{ sections: SectionData[]; metadata: ProjectMetadata }> {
  return new Promise((resolve) => {
    setTimeout(() => {
      const updatedSections = sections.map((s) => ({
        ...s,
        graphAdvice: s.content.trim() ? { ...MOCK_GRAPH_ADVICE } : undefined,
      }));

      const updatedMetadata = {
        ...metadata,
        plot:
          metadata.plot ||
          'A journey of self-discovery triggered by an unexpected event that forces the protagonist out of their comfort zone.',
        characters: [...new Set([...metadata.characters, 'Mysterious Mentor'])],
      };

      resolve({ sections: updatedSections, metadata: updatedMetadata });
    }, 3000);
  });
}

export function makeSectionRow(content = '', isEditing = false): SectionData {
  return {
    id: crypto.randomUUID(),
    content,
    isEditing,
    status: 'draft',
  };
}
