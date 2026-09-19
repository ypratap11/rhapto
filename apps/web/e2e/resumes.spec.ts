import type { Page } from "@playwright/test";
import { expect, test } from "./fixtures";

type JobSummary = { id: string; title: string | null; company: string | null };

async function fetchJson<T>(path: string): Promise<T> {
  const apiUrl = process.env.RHAPTO_PUBLIC_API_URL ?? "http://localhost:8000";
  const token = process.env.RHAPTO_API_TOKEN ?? "";
  const res = await fetch(`${apiUrl}${path}`, { headers: { Authorization: `Bearer ${token}` } });
  if (!res.ok) throw new Error(`GET ${path} failed: ${res.status} ${await res.text()}`);
  return (await res.json()) as T;
}

async function pickRecommendedJob(skip: number): Promise<JobSummary> {
  const jobs = await fetchJson<JobSummary[]>("/api/v1/jobs?recommended=true&sort=fit");
  const job = jobs[skip];
  if (!job) throw new Error(`Fewer than ${skip + 1} recommended jobs left to tailor.`);
  return job;
}

/** This file's tailors need at least one track to select in the Mode/Track pickers
 * (TailorButton's `selectedTrackId` falls back to `tracks.data?.[0]?.id`, and the tailor endpoint
 * needs a real `track_id`). profile.example ships two, but profile.spec.ts deletes both of them
 * partway through its own test before re-adding one via the field picker — so this file's tailors
 * only have a track to use if profile.spec.ts already ran (and finished) first, which nothing
 * beyond Playwright's default alphabetical file order actually guarantees (a shard split, a
 * rename, or running this file alone would all break it, silently, several files away from the
 * cause — exactly what happened once during this task's own development). Assert/create a track
 * directly rather than depend on that ordering.
 */
async function ensureTrackExists(): Promise<void> {
  const tracks = await fetchJson<{ id: string }[]>("/api/v1/profile/tracks");
  if (tracks.length > 0) return;
  const bases = await fetchJson<{ id: string }[]>("/api/v1/profile/bases");
  const apiUrl = process.env.RHAPTO_PUBLIC_API_URL ?? "http://localhost:8000";
  const token = process.env.RHAPTO_API_TOKEN ?? "";
  const track = {
    id: "e2e-resumes-fallback",
    name: "E2E fallback track",
    description: "Created by resumes.spec.ts because no track existed yet.",
    keywords: [],
    resume_base: bases[0]?.id ?? "default",
    min_fit: 0,
  };
  const res = await fetch(`${apiUrl}/api/v1/profile/tracks/${track.id}`, {
    method: "PUT",
    headers: { Authorization: `Bearer ${token}`, "content-type": "application/json" },
    body: JSON.stringify(track),
  });
  if (!res.ok) throw new Error(`Could not create a fallback track: ${res.status} ${await res.text()}`);
}

test.beforeAll(async () => {
  await ensureTrackExists();
});

async function tailorInBlocksMode(page: Page, jobId: string): Promise<void> {
  await page.goto(`/jobs/${jobId}`);
  // Explicit "Build from blocks" — see dashboard.spec.ts for why the default must not be trusted.
  await page.getByRole("combobox", { name: "Mode" }).click();
  await page.getByRole("option", { name: "Build from blocks" }).click();
  await page.getByRole("button", { name: "Tailor" }).click();
  await expect(page.getByRole("link", { name: "Review", exact: true })).toBeVisible({ timeout: 120_000 });
}

test("Skip archives the resume and the job disappears from Jobs", async ({ page }) => {
  const job = await pickRecommendedJob(0);
  const title = job.title ?? "";
  await tailorInBlocksMode(page, job.id);

  await page.goto("/resumes?tab=review");
  const row = page.getByRole("row", { name: title }).filter({ hasText: job.company ?? "" });
  await expect(row).toBeVisible();
  await row.getByRole("button", { name: "Skip" }).click();
  await expect(page.getByRole("row", { name: title })).toHaveCount(0);

  // "Disappears from /jobs" is `hidden_at` being set (jobs_repo.list_jobs filters
  // `Job.hidden_at.is_(None)` by default) — the same field NotInterestedButton/DidYouApplyPrompt's
  // Skip set. Browse (useJobsQuery/toJobsQuery) has no title-search parameter at all — only the
  // "Search" button's *live* search does, and a live search for one specific, already-known job's
  // exact title is not a dependable signal (it depends on what external sources return right now,
  // not on this app's own hidden-job filter) — so the API is asked directly for the fact the UI's
  // filter itself is built on.
  const job2 = await fetchJson<{ hidden_at: string | null }>(`/api/v1/jobs/${job.id}`);
  expect(job2.hidden_at, "job.hidden_at should be set once Skip has hidden it").not.toBeNull();
});

test("a blocked resume shows its guardrail violations on the review page", async ({ page }) => {
  const job = await pickRecommendedJob(0);
  await tailorInBlocksMode(page, job.id);
  await page.getByRole("link", { name: "Review", exact: true }).click();
  await expect(page).toHaveURL(/\/packages\/[^/]+$/);

  // Edit a bullet to add a number this block's own source text never had. The guardrail
  // (no-unverified-metrics, engine/guardrails/metrics.py) flags any number in rendered text that
  // is not present in its source block — verified or not — so this reliably produces a genuine
  // "blocked" version from nothing but profile.example content plus a fabricated, harmless metric.
  const editButton = page.getByRole("button", { name: "Edit bullet" }).first();
  await editButton.click();
  const textarea = page.getByRole("textbox", { name: "Edit bullet" });
  const original = await textarea.inputValue();
  await textarea.fill(`${original} This lifted throughput by 37%.`);
  await page.getByRole("button", { name: "Save bullet" }).click();
  await page.getByRole("button", { name: "Save as new version" }).click();
  await expect(page).toHaveURL(/\/packages\/[^/]+$/);

  const guardrails = page.getByRole("region", { name: "Guardrails" });
  await expect(guardrails).toContainText("blocked");
  const violations = guardrails.getByRole("listitem");
  await expect(violations).not.toHaveCount(0);
  await expect(violations.filter({ hasText: "37" })).not.toHaveCount(0);

  await page.goto("/resumes?tab=blocked");
  await expect(page.getByRole("row", { name: job.title ?? "" }).filter({ hasText: job.company ?? "" })).toBeVisible();
});
