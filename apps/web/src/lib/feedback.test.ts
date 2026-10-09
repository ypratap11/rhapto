import { readdirSync } from "node:fs";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import visibility from "./edge-visibility.json";
import {
  areaForPath,
  clearDraft,
  contextForPath,
  draftKey,
  FEEDBACK_HIDDEN_ROUTES,
  loadDraft,
  saveDraft,
  SURVEY_STEPS,
  toSurveyBody,
  type FeedbackIn,
  type SurveyDraft,
} from "./feedback";

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
    ["/start", "coach"],
    ["/start/", "coach"],
    ["/somewhere-new", "other"],
    ["/", "other"],
  ])("%s -> %s", (path, area) => {
    expect(areaForPath(path)).toBe(area);
  });

  it("does not let a prefix of one route claim a longer, different one", () => {
    expect(areaForPath("/jobsfoo")).toBe("other");
    expect(areaForPath("/profiles")).toBe("other");
    expect(areaForPath("/starter")).toBe("other");
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

const USER_A = "11111111-1111-4111-8111-111111111111";
const USER_B = "22222222-2222-4222-8222-222222222222";

function draft(overrides: Partial<SurveyDraft> = {}): SurveyDraft {
  return {
    savedAt: Date.now(),
    step: 2,
    answers: { getting_started: { ease: 4, stuck: "The invite email took a while." } },
    ...overrides,
  };
}

describe("survey draft (browser storage)", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("keys the draft per user", () => {
    expect(draftKey(USER_A)).toBe(`rhapto.feedback.draft.v1.${USER_A}`);
    expect(draftKey(USER_A)).not.toBe(draftKey(USER_B));
  });

  it("round-trips a saved draft and clears it", () => {
    const d = draft();
    saveDraft(USER_A, d);
    expect(loadDraft(USER_A)).toEqual(d);
    clearDraft(USER_A);
    expect(loadDraft(USER_A)).toBeNull();
  });

  it("isolates drafts between users sharing a browser", () => {
    saveDraft(USER_A, draft());
    expect(loadDraft(USER_B)).toBeNull();
    clearDraft(USER_B);
    expect(loadDraft(USER_A)).not.toBeNull();
  });

  it("expires a draft after 7 days", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-10-01T00:00:00Z"));
    saveDraft(USER_A, draft({ savedAt: Date.now() }));
    vi.setSystemTime(new Date("2026-10-07T23:59:00Z"));
    expect(loadDraft(USER_A)).not.toBeNull();
    vi.setSystemTime(new Date("2026-10-08T00:00:01Z"));
    expect(loadDraft(USER_A)).toBeNull();
  });

  it("treats corrupt or wrongly shaped storage as no draft, without throwing", () => {
    for (const raw of ["{not json", "null", "[]", '{"savedAt":"yesterday"}', '{"savedAt":1,"step":0}']) {
      window.localStorage.setItem(draftKey(USER_A), raw);
      expect(loadDraft(USER_A)).toBeNull();
    }
  });

  it("removes an expired or corrupt draft from storage when it is read", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-10-01T00:00:00Z"));
    saveDraft(USER_A, draft({ savedAt: Date.now() }));
    vi.setSystemTime(new Date("2026-10-09T00:00:00Z"));
    expect(loadDraft(USER_A)).toBeNull();
    expect(window.localStorage.getItem(draftKey(USER_A))).toBeNull();
    window.localStorage.setItem(draftKey(USER_B), "{not json");
    expect(loadDraft(USER_B)).toBeNull();
    expect(window.localStorage.getItem(draftKey(USER_B))).toBeNull();
  });

  it("is inert, not fatal, when localStorage throws", () => {
    const boom = () => {
      throw new Error("blocked");
    };
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(boom);
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(boom);
    vi.spyOn(Storage.prototype, "removeItem").mockImplementation(boom);
    expect(() => saveDraft(USER_A, draft())).not.toThrow();
    expect(loadDraft(USER_A)).toBeNull();
    expect(() => clearDraft(USER_A)).not.toThrow();
  });
});

describe("SURVEY_STEPS", () => {
  it("defines the seven sections in spec order", () => {
    expect(SURVEY_STEPS.map((s) => s.id)).toEqual([
      "session",
      "getting_started",
      "profile",
      "finding_jobs",
      "review",
      "downloads",
      "overall",
    ]);
  });
});

describe("toSurveyBody", () => {
  it("drops empty sections, blank text, unset fields and a false quote_ok", () => {
    const body = toSurveyBody({
      savedAt: 1,
      step: 0,
      answers: {
        session: {},
        getting_started: { ease: 3, stuck: "   " },
        profile: { missing_or_confusing: "" },
        overall: { quote_ok: false },
      },
    });
    expect(body).toEqual({ form: "survey", answers: { getting_started: { ease: 3 } } });
  });

  it("keeps quote_ok when it is true and trims text", () => {
    const body = toSurveyBody({
      savedAt: 1,
      step: 6,
      answers: { overall: { would_use: "maybe", fix_first: "  Faster import  ", quote_ok: true } },
    });
    expect(body.answers).toEqual({ overall: { would_use: "maybe", fix_first: "Faster import", quote_ok: true } });
  });

  it("drops a conditional field whose condition no longer holds", () => {
    const body = toSurveyBody({
      savedAt: 1,
      step: 0,
      answers: { session: { task: "find_jobs", task_other: "left over from an earlier choice", finished: "yes" } },
    });
    expect(body.answers).toEqual({ session: { task: "find_jobs", finished: "yes" } });
  });

  it("yields a body the generated FeedbackIn type accepts, and nothing a quick form would carry", () => {
    const body: FeedbackIn = toSurveyBody({
      savedAt: 1,
      step: 4,
      answers: { review: { resume_quality: 5, flagged: "yes", flag_verdict: "right", would_have_noticed: "no" } },
    });
    expect(body.form).toBe("survey");
    expect(body.page_area).toBeUndefined();
    expect(body.job_id).toBeUndefined();
    expect(body.package_id).toBeUndefined();
  });

  it("returns an empty answers object when nothing was answered", () => {
    expect(toSurveyBody({ savedAt: 1, step: 0, answers: {} }).answers).toEqual({});
  });
});
