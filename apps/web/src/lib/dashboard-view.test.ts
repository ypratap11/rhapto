import { describe, expect, it } from "vitest";
import type { ApplicationOut, JobOut } from "@/lib/api/queries";
import {
  barLabel,
  barSegments,
  firstName,
  followUpTip,
  greeting,
  isNewToday,
  pickNextStep,
  strongMatchCount,
  summaryLine,
  tileHint,
} from "./dashboard-view";

describe("firstName", () => {
  it("takes the first word, trimmed", () => {
    expect(firstName("  Maya  Rao ")).toBe("Maya");
    expect(firstName("Maya")).toBe("Maya");
  });
  it("is empty for missing or blank names", () => {
    expect(firstName(undefined)).toBe("");
    expect(firstName(null)).toBe("");
    expect(firstName("   ")).toBe("");
  });
});

describe("greeting", () => {
  it.each([
    [0, "Good morning, Maya"],
    [11, "Good morning, Maya"],
    [12, "Good afternoon, Maya"],
    [17, "Good afternoon, Maya"],
    [18, "Good evening, Maya"],
    [23, "Good evening, Maya"],
  ])("hour %i", (hour, text) => {
    expect(greeting(hour, "Maya")).toBe(text);
  });
  it("is Welcome back with no name", () => {
    expect(greeting(9, "")).toBe("Welcome back");
    expect(greeting(9, "   ")).toBe("Welcome back");
  });
});

describe("summaryLine", () => {
  it("says both clauses", () => {
    expect(summaryLine({ strong: 5, review: 1 })).toBe("5 strong matches are waiting, and 1 resume is ready for your review.");
    expect(summaryLine({ strong: 1, review: 2 })).toBe("1 strong match is waiting, and 2 resumes are ready for your review.");
  });
  it("omits a clause whose count is zero or unknown", () => {
    expect(summaryLine({ strong: 3, review: 0 })).toBe("3 strong matches are waiting.");
    expect(summaryLine({ strong: 0, review: 2 })).toBe("2 resumes are ready for your review.");
    expect(summaryLine({ strong: 3, review: null })).toBe("3 strong matches are waiting.");
    expect(summaryLine({ strong: null, review: 1 })).toBe("1 resume is ready for your review.");
  });
  it("falls back when there is nothing true to say", () => {
    expect(summaryLine({ strong: 0, review: 0 })).toBe("Here's where your search stands.");
    expect(summaryLine({ strong: null, review: null })).toBe("Here's where your search stands.");
  });
});

const job = (id: string, fit: number | null, track = "t1") => ({ id, best_fit: fit, best_track_id: track }) as unknown as JobOut;

describe("strongMatchCount", () => {
  const tracks = [
    { id: "t1", min_fit: 70 },
    { id: "t2", min_fit: 90 },
  ];
  it("counts only the rows shown (first five) against each track's min fit", () => {
    const jobs = [job("1", 80), job("2", 70), job("3", 69), job("4", 85, "t2"), job("5", 95, "t2"), job("6", 99)];
    expect(strongMatchCount(jobs, tracks)).toBe(3); // 80, 70, 95; the sixth is not shown
  });
  it("falls back to the picker threshold for an unknown track", () => {
    expect(strongMatchCount([job("1", 99, "gone")], tracks)).toBe(1);
    expect(strongMatchCount([job("1", 1, "gone")], tracks)).toBe(0);
  });
  it("is null until tracks have loaded", () => {
    expect(strongMatchCount([job("1", 99)], undefined)).toBeNull();
  });
  it("does not count unscored jobs", () => {
    expect(strongMatchCount([job("1", null)], tracks)).toBe(0);
  });
});

describe("isNewToday", () => {
  const now = new Date("2026-10-11T12:00:00Z");
  const ago = (h: number) => new Date(now.getTime() - h * 3_600_000).toISOString();
  it("is true inside 24 hours", () => {
    expect(isNewToday(ago(23), now)).toBe(true);
    expect(isNewToday(ago(0), now)).toBe(true);
  });
  it("is false from 24 hours on", () => {
    expect(isNewToday(ago(24), now)).toBe(false);
    expect(isNewToday(ago(25), now)).toBe(false);
  });
  it("is false for an unreadable date", () => {
    expect(isNewToday("nope", now)).toBe(false);
  });
});

const app = (over: Partial<ApplicationOut>) =>
  ({ id: "a", status: "applied", applied_at: null, follow_up_at: null, job: { company: "Co", title: "TPM" }, ...over }) as unknown as ApplicationOut;

describe("followUpTip", () => {
  const now = new Date("2026-10-11T12:00:00Z");
  const daysAgo = (d: number) => new Date(now.getTime() - d * 86_400_000).toISOString();
  it("does not show at 6 days", () => {
    expect(followUpTip([app({ applied_at: daysAgo(6) })], now)).toBeNull();
  });
  it("shows at 7 days", () => {
    expect(followUpTip([app({ id: "x", applied_at: daysAgo(7) })], now)?.id).toBe("x");
  });
  it("does not show when a follow-up date is set", () => {
    expect(followUpTip([app({ applied_at: daysAgo(20), follow_up_at: daysAgo(-3) })], now)).toBeNull();
  });
  it("only looks at applied (not screening, interviewing, offer, closed) and needs a date", () => {
    const rows = [
      app({ id: "s", status: "screen", applied_at: daysAgo(30) }),
      app({ id: "i", status: "interview", applied_at: daysAgo(30) }),
      app({ id: "n", applied_at: null }),
    ];
    expect(followUpTip(rows, now)).toBeNull();
  });
  it("picks the oldest of those that qualify", () => {
    const rows = [
      app({ id: "new", applied_at: daysAgo(8) }),
      app({ id: "old", applied_at: daysAgo(30) }),
      app({ id: "set", applied_at: daysAgo(60), follow_up_at: daysAgo(-1) }),
    ];
    expect(followUpTip(rows, now)?.id).toBe("old");
  });
});

describe("tiles and bar", () => {
  const counts = { applied: 2, interviewing: 1, offer: 1, closed: 0, all: 4 };
  it("sizes segments in proportion and drops empty ones", () => {
    const segs = barSegments(counts);
    expect(segs.map((s) => s.id)).toEqual(["applied", "interviewing", "offer"]);
    expect(segs.map((s) => s.percent)).toEqual([50, 25, 25]);
  });
  it("has no segments with no applications", () => {
    expect(barSegments({ applied: 0, interviewing: 0, offer: 0, closed: 0, all: 0 })).toEqual([]);
  });
  it("says the counts in the aria label", () => {
    expect(barLabel(counts)).toBe("2 applied, 1 interviewing, 1 offer, 0 closed");
    expect(barLabel({ ...counts, offer: 2 })).toBe("2 applied, 1 interviewing, 2 offers, 0 closed");
  });
  it("has a hint for each tile, with and without a count", () => {
    expect(tileHint("review", 1)).toBe("Tailored, not sent yet");
    expect(tileHint("review", 0)).toBe("Nothing waiting");
    expect(tileHint("applied", 1)).toBe("Waiting to hear back");
    expect(tileHint("applied", 0)).toBe("Nothing sent yet");
    expect(tileHint("interviewing", 0)).toBe("Nothing scheduled");
    expect(tileHint("interviewing", 2)).toBe("2 in progress");
    expect(tileHint("offer", 0)).toBe("Keep going");
    expect(tileHint("offer", 1)).toBe("Congratulations");
  });
});

describe("pickNextStep", () => {
  const draft = { id: "p1", job_id: "j1", company: "Rigetti", title: "TPM", best_fit: 78 };
  const due = { applicationId: "a1", company: "Sunrun", title: "PM" };
  const top = job("jt", 90);
  const base = {
    dashboard: "ready" as const,
    reviewCount: 0,
    drafts: "ready" as const,
    newestDraft: undefined as typeof draft | undefined,
    dueFollowUp: null as typeof due | null,
    jobs: "ready" as const,
    topJob: undefined as JobOut | undefined,
  };

  it("1: review wins when a draft is waiting", () => {
    expect(pickNextStep({ ...base, reviewCount: 2, newestDraft: draft, dueFollowUp: due, topJob: top })).toEqual({ kind: "review", draft });
  });
  it("2: a due follow-up when nothing is waiting for review", () => {
    expect(pickNextStep({ ...base, dueFollowUp: due, topJob: top })).toEqual({ kind: "followup", ...due });
  });
  it("3: tailor the top recommended job", () => {
    expect(pickNextStep({ ...base, topJob: top })).toEqual({ kind: "tailor", job: top });
  });
  it("4: nothing", () => {
    expect(pickNextStep(base)).toBeNull();
  });
  it("does not fall through to 2 or 3 while the draft list loads", () => {
    expect(pickNextStep({ ...base, reviewCount: 1, drafts: "loading", dueFollowUp: due, topJob: top })).toEqual({ kind: "loading" });
  });
  it("links to the review list when the draft list fails or comes back empty", () => {
    expect(pickNextStep({ ...base, reviewCount: 1, drafts: "error", dueFollowUp: due, topJob: top })).toEqual({ kind: "review-list" });
    expect(pickNextStep({ ...base, reviewCount: 1, drafts: "ready", dueFollowUp: due, topJob: top })).toEqual({ kind: "review-list" });
  });
  it("waits while the dashboard loads, and skips review when it failed", () => {
    expect(pickNextStep({ ...base, dashboard: "loading", topJob: top })).toEqual({ kind: "loading" });
    expect(pickNextStep({ ...base, dashboard: "error", reviewCount: 0, topJob: top })).toEqual({ kind: "tailor", job: top });
  });
  it("waits for jobs before choosing to show nothing", () => {
    expect(pickNextStep({ ...base, jobs: "loading" })).toEqual({ kind: "loading" });
    expect(pickNextStep({ ...base, jobs: "error" })).toBeNull();
  });
});
