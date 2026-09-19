import { expect, test } from "./fixtures";

type JobSummary = { id: string; title: string | null; company: string | null };

/** Same endpoint, same sort as the Dashboard's own Recommended roles panel
 * (useRecommendedJobs -> GET /api/v1/jobs?recommended=true&sort=fit), so `jobs[0]` here is the
 * same job the first card on the page renders. */
async function pickFirstRecommendedJob(): Promise<JobSummary> {
  const apiUrl = process.env.RHAPTO_PUBLIC_API_URL ?? "http://localhost:8000";
  const token = process.env.RHAPTO_API_TOKEN ?? "";
  const res = await fetch(`${apiUrl}/api/v1/jobs?recommended=true&sort=fit`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error(`GET /api/v1/jobs failed: ${res.status} ${await res.text()}`);
  const jobs = (await res.json()) as JobSummary[];
  const job = jobs[0];
  if (!job) throw new Error("No recommended job found — cannot exercise the Dashboard's Tailor flow.");
  return job;
}

test("the dashboard reports real numbers and a recommendation reaches a resume", async ({ page }) => {
  // Picked through the API, before the page even loads, and then found by its own title/company —
  // not by card position. `staleTime: 30_000` plus `refetchOnWindowFocus` means a background
  // refetch between reading a card's text and clicking a lazily re-resolved locator could otherwise
  // tailor a different job than the one the final assertion below looks for (job-page.spec.ts and
  // resumes.spec.ts hit the same hazard and solved it the same way: pick the job through the API
  // first).
  const job = await pickFirstRecommendedJob();
  const role = job.title ?? "";
  const company = job.company ?? "";

  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toContainText(/new role|Nothing new yet/);

  // The checklist's <ul> has no accessible name of its own (it is named only by the enclosing
  // <section>'s aria-labelledby), so the section itself — exposed as role="region" once it has an
  // accessible name — is what carries "Profile checklist", not the list.
  const checklist = page.getByRole("region", { name: /profile checklist/i });
  await expect(checklist.getByRole("listitem")).toHaveCount(6);

  // Found by identity (title + company), not position: even if the grid re-renders between this
  // and the click, this locator still resolves to `job`'s own card.
  const card = page.getByRole("article").filter({ hasText: role }).filter({ hasText: company });
  await card.getByRole("link", { name: "Tailor" }).click();
  await expect(page).toHaveURL(new RegExp(`/jobs/${job.id}$`));

  // Explicit "Build from blocks": this stack's uploaded resume document (Profile > Resume
  // template) is shared across the whole suite and not reset by profile.example's import (see
  // global-setup.ts). Leaving Mode on its default would silently switch to "tune" and render that
  // document's real content on the review page below.
  await page.getByRole("combobox", { name: "Mode" }).click();
  await page.getByRole("option", { name: "Build from blocks" }).click();
  await page.getByRole("button", { name: "Tailor" }).click();
  // Below playwright.config.ts's 120_000 test-level timeout so a real failure here reports this
  // assertion's own message instead of the test timing out first with no diagnosis.
  await expect(page.getByRole("link", { name: "Review", exact: true })).toBeVisible({ timeout: 90_000 });

  await page.goto("/resumes?tab=review");
  await expect(page.getByRole("row", { name: role }).filter({ hasText: company })).toBeVisible();
});
