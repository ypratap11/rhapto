import { describe, expect, it } from "vitest";
import { flowPrompt, jobState, nextUp, stepForPath } from "./flow";
import type { JobOut } from "./api/queries";

const base = (over: Partial<JobOut>): JobOut => ({
  id: "j", source: "manual", company: "ExampleCo", title: "Data PM", location: null, url: null, jd_text: "x",
  extracted: null, discovered_at: "2026-09-01T00:00:00Z", latest_package: null, application_status: null,
  best_track_id: "data-pm", best_fit: 70, bucket: "fit", rescued: false, repost_of: null, posted_at: null, scores: [],
  ...over,
});

describe("flow", () => {
  it("derives the job state", () => {
    expect(jobState(base({}))).toBe("tailor");
    const pkg = { id: "p", version: 1, status: "draft", created_at: "2026-09-01T00:00:00Z" };
    expect(jobState(base({ latest_package: pkg }))).toBe("review");
    expect(jobState(base({ latest_package: pkg, application_status: "queued" }))).toBe("review");
    expect(jobState(base({ latest_package: pkg, application_status: "applied" }))).toBe("applied");
    expect(jobState(base({ latest_package: pkg, application_status: "interview" }))).toBe("applied");
  });
  it("ranks next up by fit, skipping applied, skipped and unscored jobs", () => {
    const jobs = [
      base({ id: "a", best_fit: 60 }),
      base({ id: "b", best_fit: 90 }),
      base({ id: "c", best_fit: 95, latest_package: { id: "p", version: 1, status: "draft", created_at: "" }, application_status: "applied" }),
      base({ id: "d", best_fit: null }),
      base({ id: "e", best_fit: 80 }),
    ];
    expect(nextUp(jobs, ["e"], 5).map((j) => j.id)).toEqual(["b", "a"]);
    expect(nextUp(jobs, [], 1).map((j) => j.id)).toEqual(["b"]);
  });
  it("maps paths to steps and builds the prompt", () => {
    expect(stepForPath("/", false)).toBe(0);
    expect(stepForPath("/", true)).toBe(1);
    expect(stepForPath("/jobs/j/packages/p", false)).toBe(2);
    expect(stepForPath("/pipeline", false)).toBe(3);
    expect(flowPrompt({ needsReview: 3, next: null })).toEqual({ text: "3 packages ready to review", href: "/packages?filter=review" });
    expect(flowPrompt({ needsReview: 0, next: base({ id: "z", best_fit: 72 }) })).toEqual({ text: "Next: tailor ExampleCo, Data PM (fit 72)", href: "/#job-z" });
    expect(flowPrompt({ needsReview: 0, next: null })).toBeNull();
  });
});
