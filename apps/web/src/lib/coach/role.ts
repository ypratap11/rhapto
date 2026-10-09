import type { TaxonomyField, TaxonomyOut, TaxonomyRole } from "@/lib/api/portal";
import { useAnswers, useBases, usePutAnswers, usePutTrack, useTracks, type ImportedLocation, type ImportedTrack, type Track } from "@/lib/api/queries";
import { joinList } from "@/lib/profile-forms";
import { PICKER_MIN_FIT, trackFromRole } from "@/lib/taxonomy";

/** The resume_base a coach-created track falls back to when the profile has no bases yet. Same slug and
 * reason as `DEFAULT_RESUME_BASE_ID` in ImportResume.tsx: `synthesize_bases` turns any valid slug into a
 * real, resolvable base; an empty string would crash it. */
export const COACH_BASE_ID = "imported-default";

export type RoleSource =
  | { kind: "proposed"; track: ImportedTrack }
  | { kind: "taxonomy"; field: TaxonomyField; role: TaxonomyRole };

export function resumeBaseFor(bases: { id: string }[] | undefined): string {
  return bases && bases.length > 0 ? bases[0]!.id : COACH_BASE_ID;
}

/** One track, always at min_fit 60 (`PICKER_MIN_FIT`), so the step 4 label has a single threshold. */
export function coachTrack(source: RoleSource, resumeBase: string): Track {
  if (source.kind === "taxonomy") return trackFromRole(source.field, source.role, resumeBase);
  const t = source.track;
  return {
    id: t.id,
    name: t.name,
    description: null,
    keywords: t.keywords ?? [],
    min_fit: PICKER_MIN_FIT,
    resume_base: resumeBase,
    field: t.field,
    role: t.role,
  };
}

/** The answers PUT replaces the whole map, so this merges into what exists, exactly as
 * `ImportResume.handleAccept` does. Null when the import found no location (write nothing). */
export function mergeLocationAnswers(existing: Record<string, string>, location: ImportedLocation): Record<string, string> | null {
  const { location_home, remote_ok } = location;
  const preferred = location.location_preferred ?? [];
  if (!location_home && preferred.length === 0 && !remote_ok) return null;
  return {
    ...existing,
    ...(location_home ? { location_home } : {}),
    ...(preferred.length > 0 ? { location_preferred: joinList(preferred) } : {}),
    ...(remote_ok ? { remote_ok } : {}),
  };
}

/** The typeahead behind "Something else": role names and title phrases. */
export function searchRoles(taxonomy: TaxonomyOut, query: string, limit = 8): { field: TaxonomyField; role: TaxonomyRole }[] {
  const q = query.trim().toLowerCase();
  if (!q) return [];
  const out: { field: TaxonomyField; role: TaxonomyRole }[] = [];
  for (const field of taxonomy.fields) {
    for (const role of field.roles) {
      if (role.name.toLowerCase().includes(q) || role.titles.some((t) => t.toLowerCase().includes(q))) out.push({ field, role });
      if (out.length >= limit) return out;
    }
  }
  return out;
}

/** The coach saves ONE track and the location answers, and NO blocks (spec 2: tune mode never reads
 * blocks, and `PUT /profile/blocks/{id}` is an upsert that could overwrite a returning tester's verified
 * ones). Not `ImportResume.handleAccept`, which writes every proposed track and every block.
 * `ready` is false until `answers` and `bases` have loaded: saving before then would PUT an answers map
 * holding only the location keys and wipe the rest. */
export function useSaveCoachRole() {
  const answers = useAnswers();
  const bases = useBases();
  const putTrack = usePutTrack();
  const putAnswers = usePutAnswers();
  const tracks = useTracks();
  const ready = answers.data !== undefined && bases.data !== undefined && tracks.data !== undefined;

  async function save(source: RoleSource, location: ImportedLocation | null): Promise<Track> {
    const existing = answers.data;
    if (existing === undefined || bases.data === undefined || tracks.data === undefined) throw new Error("profile not loaded yet");
    // A tester who already has this role keeps their own track: PUT /profile/tracks/{id} is an upsert and
    // would silently replace their keywords, min_fit and base. Its scores already exist, and readiness
    // (spec 3.3) is untouched because score_requested_at only moves on a save.
    const wanted = source.kind === "proposed" ? source.track.id : source.role.id;
    const have = tracks.data.find((t) => t.id === wanted);
    const track = have ?? coachTrack(source, resumeBaseFor(bases.data));
    // ANSWERS FIRST, THEN THE TRACK. Each of these PUTs may enqueue `rescore_jobs` (a changed location
    // answer does; a track always does), and a rescore that loses the per-user lock is re-enqueued 30 s
    // later. Saving the track last makes the last rescore the one that knows both the new track and the
    // new location, and `track=<id>` only matches after a rescore that knows the track, so step 3's
    // readiness signal can never come from a pass that scored with the old location.
    const merged = location ? mergeLocationAnswers(existing, location) : null;
    if (merged) await putAnswers.mutateAsync(merged);
    if (!have) await putTrack.mutateAsync(track);
    return track;
  }

  return { ready, isSaving: putTrack.isPending || putAnswers.isPending, save };
}
