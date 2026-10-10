import { expect, test } from "./fixtures";

type JobSummary = { id: string; title: string | null; company: string | null };

/** Same endpoint, same sort as the Dashboard's own Recommended for you list
 * (useRecommendedJobs -> GET /api/v1/jobs?recommended=true&sort=fit), so `jobs[0]` here is the
 * same job the first row on the page renders. */
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

test("the dashboard lists applications and recommendations, and a recommendation reaches a resume", async ({ page }) => {
  // Picked through the API, before the page even loads, and then found by its own title/company —
  // not by card position. `staleTime: 30_000` plus `refetchOnWindowFocus` means a background
  // refetch between reading a card's text and clicking a lazily re-resolved locator could otherwise
  // tailor a different job than the one the final assertion below looks for (job-page.spec.ts and
  // resumes.spec.ts hit the same hazard and solved it the same way: pick the job through the API
  // first).
  const job = await pickFirstRecommendedJob();
  const role = job.title ?? "";
  const company = job.company ?? "";

  await page.goto("/dashboard");
  await expect(page.getByRole("heading", { level: 1, name: "Dashboard" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Your applications" })).toBeVisible();
  const recommended = page.getByRole("region", { name: "Recommended for you" });
  await expect(recommended).toBeVisible();

  // Found by identity (title + company), not position: even if the list re-renders between this
  // and the click, this locator still resolves to `job`'s own row. A row's Tailor starts the
  // tune-mode task and hands over to the guided flow, which follows it.
  const row = recommended.getByRole("listitem").filter({ hasText: role }).filter({ hasText: company });
  await row.getByRole("button", { name: "Tailor" }).click();
  await expect(page).toHaveURL(/\/start\?task=/);

  // The tailored resume lands in the review tab once the task finishes. Reload until it does, below
  // playwright.config.ts's 120_000 test-level timeout so a real failure reports this assertion's message.
  await expect(async () => {
    await page.goto("/resumes?tab=review");
    await expect(page.getByRole("row", { name: role }).filter({ hasText: company })).toBeVisible({ timeout: 3_000 });
  }).toPass({ timeout: 90_000 });
});
