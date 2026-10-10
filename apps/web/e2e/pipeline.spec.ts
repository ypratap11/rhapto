import type { Page } from "@playwright/test";
import { expect, test } from "./fixtures";

type JobSummary = { id: string; url: string | null; company: string | null; title: string | null };

async function pickApplyableJob(): Promise<JobSummary> {
  const apiUrl = process.env.RHAPTO_PUBLIC_API_URL ?? "http://localhost:8000";
  const token = process.env.RHAPTO_API_TOKEN ?? "";
  const res = await fetch(`${apiUrl}/api/v1/jobs?recommended=true&sort=fit`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error(`GET /api/v1/jobs failed: ${res.status} ${await res.text()}`);
  const jobs = (await res.json()) as JobSummary[];
  const withUrl = jobs.find((j) => j.url);
  if (!withUrl) throw new Error("No recommended job with a posting url found.");
  return withUrl;
}

/** Creates a fresh application for `job` via the same Tailor -> Mark ready -> Apply -> Did you
 * apply flow job-page.spec.ts exercises, so this spec never touches an application it didn't
 * create itself (this dev stack already has real applications from before this suite existed). */
async function createApplication(page: Page, job: JobSummary): Promise<void> {
  await page.goto(`/jobs/${job.id}`);
  await page.getByRole("combobox", { name: "Mode" }).click();
  await page.getByRole("option", { name: "Build from blocks" }).click();
  await page.getByRole("button", { name: "Tailor" }).click();
  const reviewLink = page.getByRole("link", { name: "Review", exact: true });
  // Below playwright.config.ts's 120_000 test-level timeout — see dashboard.spec.ts.
  await expect(reviewLink).toBeVisible({ timeout: 90_000 });

  await page.goto("/resumes?tab=review");
  const row = page.getByRole("row", { name: job.title ?? "" }).filter({ hasText: job.company ?? "" });
  await row.getByRole("button", { name: "Mark ready" }).click();
  await expect(row.getByRole("button", { name: "Mark ready" })).toHaveCount(0);

  await page.goto(`/jobs/${job.id}`);
  const popupPromise = page.waitForEvent("popup");
  await page.getByRole("button", { name: "Apply" }).click();
  const popup = await popupPromise;
  await popup.close();
  await page.bringToFront();
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await page.getByRole("button", { name: "Yes" }).click();
  // markApplied is fire-and-forget from the click handler's point of view — wait for its success
  // toast so the application actually exists before this function's caller navigates away.
  await expect(page.getByText("Added to your applications")).toBeVisible();
}

/** Opens the application sheet for `job` from the Dashboard's "Your applications" list. Found by
 * company and role together: this dev stack already has several applications at the same company. */
async function openApplication(page: Page, job: JobSummary) {
  const section = page.getByRole("region", { name: "Your applications" });
  await section.getByRole("button", { name: job.company ?? "" }).filter({ hasText: job.title ?? "" }).click();
  return page.getByRole("dialog", { name: job.company ?? "" });
}

test("the old Pipeline addresses land on the Dashboard", async ({ page }) => {
  await page.goto("/pipeline");
  await expect(page).toHaveURL(/\/dashboard$/);
  await page.goto("/pipeline/board");
  await expect(page).toHaveURL(/\/dashboard$/);
});

test("an application moves to Interviewing in its sheet, takes a follow-up, then Closed records a reason", async ({ page }) => {
  const job = await pickApplyableJob();
  await createApplication(page, job);

  await page.goto("/dashboard");
  await expect(page.getByRole("heading", { name: "Your applications" })).toBeVisible();
  let sheet = await openApplication(page, job);

  // The trigger shows words, never the raw status value.
  const statusSelect = sheet.getByRole("combobox", { name: "Status" });
  await statusSelect.click();
  await page.getByRole("option", { name: "Interviewing" }).click();
  await expect(statusSelect).toContainText("Interviewing");

  const today = new Date().toISOString().slice(0, 10);
  await sheet.locator("#follow-up-date").fill(today);
  await sheet.getByRole("button", { name: "Save follow-up" }).click();
  await expect(page.getByText("Follow-up saved")).toBeVisible();
  await page.keyboard.press("Escape");

  // The Interviewing chip now holds it.
  await page.getByRole("button", { name: /^Interviewing/ }).click();
  sheet = await openApplication(page, job);

  await sheet.getByRole("combobox", { name: "Status" }).click();
  await page.getByRole("option", { name: "Closed", exact: true }).click();
  const reasonSelect = sheet.getByRole("combobox", { name: "Closed reason" });
  await reasonSelect.click();
  await page.getByRole("option", { name: "No response" }).click();
  await expect(reasonSelect).toContainText("No response");
});
