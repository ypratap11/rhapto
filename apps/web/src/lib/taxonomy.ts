import type { TaxonomyField, TaxonomyOut, TaxonomyRole, TaxonomySuggestions } from "./api/portal";
import type { Track } from "./api/queries";

/** Spec §5: a picked role becomes a track scored at 60 — high enough to be a real shortlist, low
 * enough that a first-time user sees something. */
export const PICKER_MIN_FIT = 60;

export function trackFromRole(field: TaxonomyField, role: TaxonomyRole, resumeBase: string): Track {
  return {
    id: role.id,
    name: role.name,
    description: null,
    keywords: [...role.keywords],
    min_fit: PICKER_MIN_FIT,
    resume_base: resumeBase,
    field: field.id,
    role: role.id,
  } as Track;
}

/** GET /api/v1/taxonomy/suggestions returns a flat array of matched roles, each carrying its own
 * field id — resolve those back to the live `TaxonomyField`/`TaxonomyRole` objects rather than
 * rendering a chip from stale text, and drop any the taxonomy no longer has (e.g. renamed since
 * the resume was parsed) rather than one that cannot create a track. */
export function suggestedRoles(suggestions: TaxonomySuggestions, taxonomy: TaxonomyOut): { field: TaxonomyField; role: TaxonomyRole }[] {
  const out: { field: TaxonomyField; role: TaxonomyRole }[] = [];
  for (const s of suggestions) {
    const field = taxonomy.fields.find((f) => f.id === s.field_id);
    const role = field?.roles.find((r) => r.id === s.role_id);
    if (field && role) out.push({ field, role });
  }
  return out;
}
