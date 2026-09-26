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
  await expect(page.getByText("Added to your pipeline")).toBeVisible();
}

/** Switches the Pipeline list to `tab`, searches for `job`, and clicks its card — the search box
 * only searches within the currently active status tab (ApplicationList.tsx), so a status change
 * moves the card to a different tab as well as a different place in the list. */
async function selectApplication(page: Page, job: JobSummary, tab: string): Promise<void> {
  await page.getByRole("tab", { name: tab }).click();
  const search = page.getByRole("textbox", { name: "Search applications" });
  await search.fill(job.company ?? "");
  const card = page.getByRole("button", { name: job.company ?? "" }).filter({ hasText: job.title ?? "" });
  await card.click();
  await search.fill("");
}

/** The list column and the detail pane are a master-detail pair, and both halves of that had
 * shipped broken: the sort control overflowed the 360px list column by 61px and painted over the
 * detail heading, and the detail pane rendered the whole JD inline so the page grew to ~4,900px
 * and the two panes shared one scrollbar. jsdom cannot catch either -- both are pure layout. */
test("the list column stays inside its own column and the panes scroll independently", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/pipeline");

  const sort = page.getByLabel("Sort by");
  await expect(sort).toBeVisible();
  // The card list fills the column, so its right edge is the column's right edge -- the search
  // input shares a row with the sort control and so spans only part of it.
  const cards = page.getByRole("list").first();

  const sortBox = await sort.boundingBox();
  const cardsBox = await cards.boundingBox();
  if (!sortBox || !cardsBox) throw new Error("list controls have no layout box");

  const columnRight = cardsBox.x + cardsBox.width;
  expect(sortBox.x + sortBox.width).toBeLessThanOrEqual(columnRight + 1);

  // Nothing in the list column may reach into the detail pane.
  const heading = page.getByRole("heading", { level: 2 }).first();
  const headingBox = await heading.boundingBox();
  if (!headingBox) throw new Error("detail heading has no layout box");
  expect(sortBox.x + sortBox.width).toBeLessThanOrEqual(headingBox.x);

  // The JD lives in its own scroll container, so the page itself no longer grows with it.
  const pageHeight = await page.evaluate(() => document.documentElement.scrollHeight);
  expect(pageHeight).toBeLessThan(2000);
});

test("Applied moves to Interview, a due follow-up leads the dashboard, then Closed records a reason", async ({ page }) => {
  const job = await pickApplyableJob();
  await createApplication(page, job);

  await page.goto("/pipeline");
  await selectApplication(page, job, "Applied");

  // StatusControl's SelectValue has no custom renderer, so the trigger shows the raw status
  // value ("interview"), not STATUS_LABEL's "Interview" (that label is only on the option row).
  const statusSelect = page.getByRole("combobox", { name: "Status" });
  await statusSelect.click();
  await page.getByRole("option", { name: "Interview" }).click();
  await expect(statusSelect).toContainText("interview");

  // A closed application is excluded from "due today" by design (db/repositories/dashboard.py's
  // due_followups filters `status != "closed"`), so the follow-up/red-chip check below has to run
  // on a still-open status — this is that constraint, not a shortcut.
  const today = new Date().toISOString().slice(0, 10);
  await page.locator("#follow-up-date").fill(today);
  await page.getByRole("button", { name: "Save follow-up" }).click();
  await expect(page.getByText("Follow-up saved")).toBeVisible();

  await page.goto("/dashboard");
  const activeApplications = page.getByRole("region", { name: "Active applications" });
  const firstCard = activeApplications.getByRole("listitem").first();
  await expect(firstCard).toContainText("Follow up today");
  await expect(firstCard).toContainText(job.company ?? "");

  await page.goto("/pipeline");
  await selectApplication(page, job, "Interview");
  await statusSelect.click();
  await page.getByRole("option", { name: "Closed", exact: true }).click();
  await expect(statusSelect).toContainText("closed");

  const reasonSelect = page.getByRole("combobox", { name: "Closed reason" });
  await reasonSelect.click();
  await page.getByRole("option", { name: "No response" }).click();
  await expect(reasonSelect).toContainText("no_response");
});
