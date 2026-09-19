import { readdirSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const COMPONENTS = resolve(__dirname, "../components");

describe("component layout", () => {
  it("has no queue-era directory left", () => {
    expect(readdirSync(COMPONENTS)).not.toContain("queue");
  });

  it("keeps the job components together", () => {
    const jobs = readdirSync(resolve(COMPONENTS, "jobs"));
    for (const file of ["JobCard.tsx", "TailorButton.tsx", "TaskProgress.tsx", "PollNowButton.tsx", "RunsDrawer.tsx", "AddJobDialog.tsx"]) {
      expect(jobs).toContain(file);
    }
    expect(jobs).not.toContain("FitBadge.tsx");
  });
});
