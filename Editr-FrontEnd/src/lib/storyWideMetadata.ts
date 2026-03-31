import type { EditorialReportPayload, ProjectMetadata, StoryWidePayload } from './api';

function isPlainObject(v: unknown): v is Record<string, unknown> {
  return v !== null && typeof v === 'object' && !Array.isArray(v);
}

/**
 * Derive project settings fields from persisted story-wide analysis (plot overview + cast).
 */
export function deriveSceneAndCharactersFromStoryWide(
  sw: StoryWidePayload | null | undefined,
): { scene: string; characters: string[] } {
  if (!sw) return { scene: '', characters: [] };

  let scene = '';
  const po = sw.plot_overview;
  if (po && typeof po === 'object' && !Array.isArray(po)) {
    const parts: string[] = [];
    for (const key of ['story_point', 'plot_summary'] as const) {
      const v = po[key];
      if (typeof v === 'string' && v.trim()) parts.push(v.trim());
    }
    const stakes = po.stakes;
    if (typeof stakes === 'string' && stakes.trim()) parts.push(`Stakes: ${stakes.trim()}`);
    const themes = po.theme_hypotheses;
    if (Array.isArray(themes)) {
      const t = themes
        .filter((x): x is string => typeof x === 'string' && x.trim().length > 0)
        .join('; ');
      if (t) parts.push(`Themes: ${t}`);
    }
    scene = parts.join('\n\n');
  }

  const characters: string[] = [];
  const cdb = sw.character_database;
  if (cdb && typeof cdb === 'object' && !Array.isArray(cdb)) {
    const raw = (cdb as { characters?: unknown }).characters;
    if (Array.isArray(raw)) {
      for (const row of raw) {
        if (!row || typeof row !== 'object') continue;
        const name = (row as { canonical_name?: unknown }).canonical_name;
        if (typeof name === 'string' && name.trim()) characters.push(name.trim());
      }
    }
  }

  return { scene, characters };
}

/** Enrich metadata from latest analysis report (summary, scene, cast when model produced them). */
export function mergeMetadataFromAnalysisReport(m: ProjectMetadata, report: EditorialReportPayload | null | undefined): ProjectMetadata {
  const derived = deriveSceneAndCharactersFromStoryWide(report?.story_wide);
  const base: ProjectMetadata = {
    ...m,
    plot: report?.document_summary ?? m.plot,
    ...(derived.scene.trim() ? { scene: derived.scene } : {}),
    ...(derived.characters.length ? { characters: derived.characters } : {}),
  };

  const gi = report?.genre_intention;
  if (!isPlainObject(gi)) return base;

  const fromRun: Partial<ProjectMetadata> = {};
  if (typeof gi.genre === 'string' && gi.genre.trim()) {
    fromRun.genre = gi.genre.trim().replace(/_/g, ' ');
  }
  if (Array.isArray(gi.subgenre_tags)) {
    fromRun.subgenreTags = gi.subgenre_tags
      .filter((x): x is string => typeof x === 'string')
      .map((x) => x.trim())
      .filter(Boolean);
  }
  if (Array.isArray(gi.tone_descriptors)) {
    fromRun.toneDescriptors = gi.tone_descriptors
      .filter((x): x is string => typeof x === 'string')
      .map((x) => x.trim())
      .filter(Boolean);
  }
  if (Array.isArray(gi.reference_authors)) {
    fromRun.referenceAuthors = gi.reference_authors
      .filter((x): x is string => typeof x === 'string')
      .map((x) => x.trim())
      .filter(Boolean);
  }
  if (typeof gi.short_story_single_chapter === 'boolean') {
    fromRun.shortStorySingleChapter = gi.short_story_single_chapter;
  }

  return { ...base, ...fromRun };
}
