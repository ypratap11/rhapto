import { describe, expect, it } from "vitest";
import { jobsSubtitle } from "./jobs-view";

describe("jobsSubtitle", () => {
  it("counts the stored jobs", () => {
    expect(jobsSubtitle({ count: 12, newToday: 0, live: false })).toBe("12 jobs match your roles");
  });
  it("adds the new-today clause only when there is one", () => {
    expect(jobsSubtitle({ count: 12, newToday: 3, live: false })).toBe("12 jobs match your roles · 3 new today");
    expect(jobsSubtitle({ count: 12, newToday: 0, live: false })).not.toMatch(/new today/);
  });
  it("uses the singular", () => {
    expect(jobsSubtitle({ count: 1, newToday: 0, live: false })).toBe("1 job matches your roles");
    expect(jobsSubtitle({ count: 1, newToday: 1, live: false })).toBe("1 job matches your roles · 1 new today");
    expect(jobsSubtitle({ count: 1, newToday: 0, live: true })).toBe("1 job found");
  });
  it("words a live search as found, with no new-today clause", () => {
    expect(jobsSubtitle({ count: 7, newToday: 4, live: true })).toBe("7 jobs found");
  });
  it("says nothing for zero jobs", () => {
    expect(jobsSubtitle({ count: 0, newToday: 0, live: false })).toBeNull();
    expect(jobsSubtitle({ count: 0, newToday: 0, live: true })).toBeNull();
  });
});
