import { expect, test } from "./fixtures";

type JobSummary = { id: string; url: string | null; company: string | null; title: string | null; latest_package: unknown };

async function pickApplyableJob(): Promise<JobSummary> {
  const apiUrl = process.env.RHAPTO_PUBLIC_API_URL ?? "http://localhost:8000";
  const token = process.env.RHAPTO_API_TOKEN ?? "";
  const res = await fetch(`${apiUrl}/api/v1/jobs?recommended=true&sort=fit`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error(`GET /api/v1/jobs failed: ${res.status} ${await res.text()}`);
  const jobs = (await res.json()) as JobSummary[];
  // Apply opens `job.url` in a new tab (JobHeader.onApply) — a job with no posting URL (some of
  // profile.example's own watchlist entries have none) would never open a popup at all, which
  // would make the "nothing was submitted" assertion below vacuously true. Pick one that has one.
  const withUrl = jobs.find((j) => j.url);
  if (!withUrl) throw new Error("No recommended job with a posting url found — cannot exercise the Apply flow.");
  return withUrl;
}

test("Tailor, Review, Mark ready to send and Download and open the posting reach the dashboard without submitting anything", async ({ page, context }) => {
  const job = await pickApplyableJob();

  await page.goto(`/jobs/${job.id}`);
  await expect(page.getByRole("button", { name: "Tailor my resume for this job" })).toBeVisible();

  // Explicit "Full rewrite" - see dashboard.spec.ts for why the default must not be trusted.
  await page.getByText("Options", { exact: true }).click();
  await page.getByRole("radio", { name: /Full rewrite/ }).check();
  await page.getByRole("button", { name: "Tailor my resume for this job" }).click();
  const reviewLink = page.getByRole("link", { name: "Review resume", exact: true });
  // Below playwright.config.ts's 120_000 test-level timeout — see dashboard.spec.ts.
  await expect(reviewLink).toBeVisible({ timeout: 90_000 });

  await reviewLink.click();
  await expect(page).toHaveURL(/\/packages\/[^/]+$/);

  // "Mark ready to send" is the one filled button on a draft resume's page.
  await page.getByRole("button", { name: "Mark ready to send" }).click();
  await expect(page.getByRole("button", { name: "Mark ready to send" })).toHaveCount(0);

  await page.goto(`/jobs/${job.id}`);
  const applyButton = page.getByRole("button", { name: "Download and open the posting" });
  await expect(applyButton).toBeVisible();

  const popupPromise = page.waitForEvent("popup");
  await applyButton.click();
  const popup = await popupPromise;
  await popup.waitForLoadState("domcontentloaded").catch(() => undefined);
  // Rhapto never submits (CLAUDE.md rule 1): the only interaction with the employer's tab is that
  // it opened at the right address. It is closed immediately, without filling in or submitting
  // any form on it.
  expect(popup.url()).toContain(new URL(job.url as string).hostname);
  await popup.close();

  // The "Did you apply?" prompt (lib/apply-prompt.ts) only appears once the tab regains focus.
  // `bringToFront()` alone is not reliably observed as a `focus` event by the page in a headless
  // context, so it is dispatched explicitly — the same signal a real window regaining focus sends.
  await page.bringToFront();
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect(page.getByRole("heading", { name: "Did you apply?" })).toBeVisible();
  await page.getByRole("button", { name: "Yes" }).click();
  // markApplied is fire-and-forget from the click handler's point of view — wait for its success
  // toast so the application actually exists before navigating to /dashboard below.
  await expect(page.getByText("Added to your applications")).toBeVisible();

  // Multiple applications can share a company (this dev stack already has more than one Scale AI
  // application), so the title disambiguates which row is this run's.
  await page.goto("/dashboard");
  const applicationRow = page.getByRole("region", { name: "Your applications" }).getByRole("button", { name: job.company ?? "" }).filter({ hasText: job.title ?? "" });
  await expect(applicationRow).toBeVisible();
});
