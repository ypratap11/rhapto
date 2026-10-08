import { describe, expect, it } from "vitest";
import { PICKER_MIN_FIT, suggestedRoles, trackFromRole } from "./taxonomy";
import type { TaxonomyField, TaxonomyOut, TaxonomySuggestions } from "./api/portal";

// Fictional field/role data, same shape GET /api/v1/taxonomy returns (packages/schemas/taxonomy.yaml).
const field: TaxonomyField = {
  id: "program-and-project-management",
  name: "Program and Project Management",
  themuse_category: "Project Management",
  adzuna_category: "PM Jobs",
  roles: [
    { id: "technical-program-manager", name: "Technical Program Manager", keywords: ["program manager", "tpm", "cross-functional"], titles: ["technical program manager"], exclude_titles: [] },
    { id: "program-manager", name: "Program Manager", keywords: ["program manager"], titles: ["program manager"], exclude_titles: [] },
  ],
};
const taxonomy: TaxonomyOut = { fields: [field] };

describe("taxonomy", () => {
  it("turns a role into a track with the curated keywords and a 60 threshold", () => {
    const role = field.roles[1];
    if (!role) throw new Error("fixture role missing");
    expect(trackFromRole(field, role, "default")).toEqual({
      id: "program-manager",
      name: "Program Manager",
      description: null,
      keywords: ["program manager"],
      min_fit: PICKER_MIN_FIT,
      resume_base: "default",
      field: "program-and-project-management",
      role: "program-manager",
    });
    expect(PICKER_MIN_FIT).toBe(60);
  });

  it("resolves the parser's suggestions back to fields and roles, dropping unknown ids", () => {
    // GET /api/v1/taxonomy/suggestions returns a flat array of TaxonomySuggestionOut — one entry
    // per matched role, carrying both the role's and its field's id and name.
    const suggestions: TaxonomySuggestions = [
      {
        field_id: "program-and-project-management",
        field_name: "Program and Project Management",
        role_id: "program-manager",
        role_name: "Program Manager",
        matched_title: "Program Manager, Platform",
      },
      // A role the taxonomy no longer has (e.g. renamed since the resume was parsed) must be
      // dropped rather than producing a chip that cannot create a track.
      { field_id: "nope", field_name: "Nope", role_id: "nope", role_name: "Nope", matched_title: "Nope" },
    ];
    expect(suggestedRoles(suggestions, taxonomy).map((s) => s.role.id)).toEqual(["program-manager"]);
  });
});
