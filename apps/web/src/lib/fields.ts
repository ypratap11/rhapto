/** The taxonomy fields a user can usefully filter by: the ones they actually have a track in.
 *
 * `GET /jobs?field=<id>` resolves the field to that user's tracks and, finding none, applies
 * `best_track_id IN ()` — an empty result. That is the correct answer to "jobs in a field you do
 * not follow", but from the UI it is indistinguishable from "no jobs match right now".
 *
 * Offering the full taxonomy therefore means most entries silently return nothing: a user whose
 * three tracks are all Program & Project Management is shown twelve fields, eleven of which are
 * dead. Filtering the list here is what keeps a chosen filter honest — every option left can
 * return something.
 */
export function fieldsWithTracks<F extends { id: string }, T extends { field?: string | null }>(
  all: readonly F[],
  tracks: readonly T[] | undefined,
): F[] {
  // Undefined means the tracks query has not resolved yet. Showing nothing would make the control
  // flicker empty on every load, so the full list stands in until we know better.
  if (tracks === undefined) return [...all];
  const owned = new Set(tracks.map((t) => t.field).filter((f): f is string => Boolean(f)));
  return all.filter((f) => owned.has(f.id));
}
