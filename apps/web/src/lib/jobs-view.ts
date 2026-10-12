/** The Jobs hero's one-line summary, built only from counts that are true. Null when there is nothing to
 * say (no jobs: the empty-state explanation below already speaks). The caller passes it only once the
 * grid has settled (not loading, no API issue). `newToday` is left out for a live search, which has no
 * "new" notion. */
export function jobsSubtitle({ count, newToday, live }: { count: number; newToday: number; live: boolean }): string | null {
  if (count <= 0) return null;
  const jobs = count === 1 ? "1 job" : `${count} jobs`;
  if (live) return `${jobs} found`;
  const base = `${jobs} ${count === 1 ? "matches" : "match"} your roles`;
  return newToday > 0 ? `${base} · ${newToday} new today` : base;
}
