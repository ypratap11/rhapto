import { describe, expect, it } from "vitest";
import type { TaxonomyOut } from "@/lib/api/portal";
import { COACH_BASE_ID, coachTrack, mergeLocationAnswers, resumeBaseFor, searchRoles } from "./role";

const taxonomy = {
  fields: [
    {
      id: "program-project-management",
      name: "Program & project management",
      themuse_category: "x",
      adzuna_category: "x",
      roles: [
        { id: "technical-program-manager", name: "Technical Program Manager", keywords: ["roadmap", "stakeholders", "delivery", "risk", "cross-functional", "launch"], titles: ["technical program manager", "tpm"], exclude_titles: [] },
        { id: "project-manager", name: "Project Manager", keywords: ["plan", "budget", "schedule", "scope", "risk", "delivery"], titles: ["project manager"], exclude_titles: [] },
      ],
    },
  ],
} as unknown as TaxonomyOut;

describe("coachTrack", () => {
  const field = taxonomy.fields[0]!;
  it("builds a taxonomy track from the taxonomy's keywords at min_fit 60", () => {
    const track = coachTrack({ kind: "taxonomy", field, role: field.roles[0]! }, "my-base");
    expect(track).toMatchObject({ id: "technical-program-manager", name: "Technical Program Manager", min_fit: 60, resume_base: "my-base", field: field.id, role: "technical-program-manager", description: null });
    expect(track.keywords).toEqual(field.roles[0]!.keywords);
  });
  it("builds a proposed track at the same min_fit, so the match label has one threshold", () => {
    const track = coachTrack({ kind: "proposed", track: { id: "tpm", name: "TPM", field: "f", role: "r", keywords: ["a"] } }, COACH_BASE_ID);
    expect(track).toMatchObject({ id: "tpm", min_fit: 60, resume_base: COACH_BASE_ID, keywords: ["a"] });
  });
});

describe("resumeBaseFor", () => {
  it("uses the first existing base, else the importable default slug", () => {
    expect(resumeBaseFor([{ id: "executive" }, { id: "other" }])).toBe("executive");
    expect(resumeBaseFor([])).toBe("imported-default");
    expect(resumeBaseFor(undefined)).toBe("imported-default");
  });
});

describe("mergeLocationAnswers (the same merge ImportResume does)", () => {
  it("keeps every existing answer and adds only what the import found", () => {
    const merged = mergeLocationAnswers(
      { name: "Maya Chen", salary: "x" },
      { location_home: "Denver, CO", location_preferred: ["Boulder, CO", "Remote"], remote_ok: "yes" },
    );
    expect(merged).toEqual({ name: "Maya Chen", salary: "x", location_home: "Denver, CO", location_preferred: "Boulder, CO, Remote", remote_ok: "yes" });
  });
  it("returns null when the import found no location, so nothing is written", () => {
    expect(mergeLocationAnswers({ name: "M" }, { location_home: null, location_preferred: [], remote_ok: null })).toBeNull();
  });
});

describe("searchRoles", () => {
  it("matches role names and title phrases, case-insensitively", () => {
    expect(searchRoles(taxonomy, "tpm").map((r) => r.role.id)).toEqual(["technical-program-manager"]);
    expect(searchRoles(taxonomy, "PROJECT").map((r) => r.role.id)).toEqual(["project-manager"]);
    expect(searchRoles(taxonomy, "manager").map((r) => r.role.id)).toEqual(["technical-program-manager", "project-manager"]);
  });
  it("returns nothing for a blank query and respects the limit", () => {
    expect(searchRoles(taxonomy, "  ")).toEqual([]);
    expect(searchRoles(taxonomy, "manager", 1)).toHaveLength(1);
  });
});
