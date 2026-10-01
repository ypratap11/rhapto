import { readdirSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import visibility from "./edge-visibility.json";
import { areaForPath, contextForPath, FEEDBACK_HIDDEN_ROUTES } from "./feedback";

const JOB = "0b9f6c1e-3a4d-4e5f-8a7b-1c2d3e4f5a6b";
const PKG = "9a8b7c6d-5e4f-4a3b-8c2d-1e0f9a8b7c6d";

describe("areaForPath", () => {
  it.each([
    ["/dashboard", "dashboard"],
    ["/dashboard/", "dashboard"],
    ["/jobs", "jobs"],
    ["/jobs/", "jobs"],
    [`/jobs/${JOB}`, "job_detail"],
    [`/jobs/${JOB}/`, "job_detail"],
    [`/jobs/${JOB}/packages/${PKG}`, "review"],
    [`/jobs/${JOB}/packages/${PKG}/`, "review"],
    ["/resumes", "resumes"],
    ["/pipeline", "pipeline"],
    ["/pipeline/", "pipeline"],
    ["/pipeline/board", "pipeline"],
    ["/profile", "profile"],
    ["/settings", "settings"],
    ["/somewhere-new", "other"],
    ["/", "other"],
  ])("%s -> %s", (path, area) => {
    expect(areaForPath(path)).toBe(area);
  });

  it("does not let a prefix of one route claim a longer, different one", () => {
    expect(areaForPath("/jobsfoo")).toBe("other");
    expect(areaForPath("/profiles")).toBe("other");
  });
});

describe("contextForPath", () => {
  it("returns the job id on a job page and both ids on a review page", () => {
    expect(contextForPath(`/jobs/${JOB}`)).toEqual({ job_id: JOB });
    expect(contextForPath(`/jobs/${JOB}/packages/${PKG}`)).toEqual({ job_id: JOB, package_id: PKG });
  });

  it("returns nothing for pages without a context, or when a segment is not a UUID", () => {
    expect(contextForPath("/dashboard")).toEqual({});
    expect(contextForPath("/jobs")).toEqual({});
    expect(contextForPath("/jobs/not-a-uuid")).toEqual({});
    expect(contextForPath(`/jobs/${JOB}/packages/nope`)).toEqual({ job_id: JOB });
  });
});

const APP_DIR = join(import.meta.dirname, "..", "app");

/** Every URL the app serves a page for, with dynamic segments replaced by a UUID. */
function pageRoutes(dir = APP_DIR, prefix = ""): string[] {
  const found: string[] = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    if (entry.isFile() && /^page\.tsx?$/.test(entry.name)) found.push(prefix || "/");
    if (!entry.isDirectory()) continue;
    if (entry.name.startsWith("(") || entry.name.startsWith("_")) continue;
    const segment = /^\[.+\]$/.test(entry.name) ? JOB : entry.name;
    found.push(...pageRoutes(join(dir, entry.name), `${prefix}/${segment}`));
  }
  return found;
}

describe("area coverage (a new page without an area fails here)", () => {
  const hidden = FEEDBACK_HIDDEN_ROUTES;

  it("hides the button on exactly /, /about and /feedback", () => {
    expect([...hidden].sort()).toEqual(["/", "/about", "/feedback"]);
  });

  it("maps every edge-protected top-level route, except /api and the hidden ones, to a real area", () => {
    const routes = visibility.protectedAtEdge.filter((r) => r !== "/api" && !hidden.has(r));
    expect(routes.length).toBeGreaterThan(4); // guard on the guard
    const other = routes.filter((r) => areaForPath(r) === "other");
    expect(other, `routes with no feedback area: ${other.join(", ")}`).toEqual([]);
  });

  it("maps every page.tsx route under app/, including nested and dynamic ones", () => {
    const routes = pageRoutes().filter((r) => !hidden.has(r));
    // Prove the walk really reaches nested and dynamic pages, or the loop below is decoration.
    expect(routes).toContain("/pipeline/board");
    expect(routes).toContain(`/jobs/${JOB}/packages/${JOB}`);
    const other = routes.filter((r) => areaForPath(r) === "other");
    expect(other, `pages with no feedback area: ${other.join(", ")}`).toEqual([]);
  });
});
