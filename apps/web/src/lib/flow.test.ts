import { describe, expect, it } from "vitest";
import { flowPrompt, jobState, nextReviewPackage, nextUp } from "./flow";
import type { JobOut, PackageListItem } from "./api/queries";

const base = (over: Partial<JobOut>): JobOut => ({
  id: "j", source: "manual", company: "ExampleCo", title: "Data PM", location: null, url: null, jd_text: "x",
  extracted: null, discovered_at: "2026-09-01T00:00:00Z", latest_package: null, application_status: null,
  best_track_id: "data-pm", best_fit: 70, bucket: "fit", rescued: false, repost_of: null, posted_at: null, scores: [], also_ids: [],
  ...over,
});

const row = (over: Partial<PackageListItem>): PackageListItem => ({
  id: "p", job_id: "j", company: "ExampleCo", title: "Data PM", status: "draft", version: 1,
  created_at: "2026-09-01T00:00:00Z", best_fit: 70, best_track_id: "data-pm", application_status: null,
  mode: "blocks", violations: 0,
  ...over,
});

describe("flow", () => {
  it("derives the job state", () => {
    expect(jobState(base({}))).toBe("tailor");
    const pkg = { id: "p", version: 1, status: "draft", mode: "tune" as const, created_at: "2026-09-01T00:00:00Z" };
    expect(jobState(base({ latest_package: pkg }))).toBe("review");
    expect(jobState(base({ latest_package: pkg, application_status: "queued" }))).toBe("review");
    expect(jobState(base({ latest_package: pkg, application_status: "applied" }))).toBe("applied");
    expect(jobState(base({ latest_package: pkg, application_status: "interview" }))).toBe("applied");
  });
  it("ranks next up by fit, skipping applied, skipped and unscored jobs", () => {
    const jobs = [
      base({ id: "a", best_fit: 60 }),
      base({ id: "b", best_fit: 90 }),
      base({ id: "c", best_fit: 95, latest_package: { id: "p", version: 1, status: "draft", mode: "blocks" as const, created_at: "" }, application_status: "applied" }),
      base({ id: "d", best_fit: null }),
      base({ id: "e", best_fit: 80 }),
    ];
    expect(nextUp(jobs, ["e"], 5).map((j) => j.id)).toEqual(["b", "a"]);
    expect(nextUp(jobs, [], 1).map((j) => j.id)).toEqual(["b"]);
  });
  it("builds the flow prompt with needsReview > nextTailor > nextReview priority", () => {
    const tailorJob = base({ id: "z", best_fit: 72 });
    const reviewJob = base({
      id: "y",
      best_fit: 65,
      latest_package: { id: "p9", version: 1, status: "blocked", mode: "blocks" as const, created_at: "" },
    });
    expect(flowPrompt({ needsReview: 3, nextTailor: tailorJob, nextReview: reviewJob })).toEqual({
      text: "3 packages ready to review",
      href: "/resumes?tab=review",
    });
    expect(flowPrompt({ needsReview: 0, nextTailor: tailorJob, nextReview: reviewJob })).toEqual({
      text: "Next: tailor ExampleCo, Data PM (fit 72)",
      href: "/#job-z",
    });
    // Blocked-package case: no packages need review, but there's a review-state job.
    expect(flowPrompt({ needsReview: 0, nextTailor: null, nextReview: reviewJob })).toEqual({
      text: "Next: review ExampleCo, Data PM",
      href: "/jobs/y/packages/p9",
    });
    expect(flowPrompt({ needsReview: 0, nextTailor: null, nextReview: null })).toBeNull();
  });
  it("advances through the review queue without ping-ponging", () => {
    const list = [row({ id: "row1" }), row({ id: "row2" }), row({ id: "row3" })];
    expect(nextReviewPackage(list, "row1")?.id).toBe("row2");
    expect(nextReviewPackage(list, "row2")?.id).toBe("row3");
    expect(nextReviewPackage(list, "row3")).toBeNull();
    // A blocked (not-in-list) package goes to the first review row.
    expect(nextReviewPackage(list, "blocked-id")?.id).toBe("row1");
    expect(nextReviewPackage([], "row1")).toBeNull();
  });
});
