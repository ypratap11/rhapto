import { expect, test } from "./fixtures";

const QUERY = "engineer";

test("Search fills the grid with scored jobs, and Poll now on this page finishes", async ({ page }) => {
  await page.goto("/jobs");
  await page.getByRole("textbox", { name: "Title" }).fill(QUERY);
  await page.getByRole("button", { name: "Search", exact: true }).click();

  // The live search hits real external sources (spec §6) and answers in roughly
  // LIVE_TIMEOUT_SECONDS regardless of how many of them are slow — generous, but bounded.
  await expect(page.getByRole("article").first()).toBeVisible({ timeout: 20_000 });
  const cardCount = await page.getByRole("article").count();
  expect(cardCount).toBeGreaterThan(0);

  // Every card starts with a dashed "not scored yet" ring; the client refetches every 3s until
  // none are left or 60s have passed (useLiveSearch). Poll for zero unscored rather than a fixed
  // wait, so this both fails honestly if scoring never catches up and finishes early if it does.
  await expect
    .poll(async () => page.getByRole("img", { name: "Fit not scored yet" }).count(), { timeout: 65_000, intervals: [3_000] })
    .toBe(0);

  const saveButton = page.getByRole("button", { name: "Save this search" });
  await expect(saveButton).toBeVisible();
  await saveButton.click();
  // SaveSearchButton unmounts once `saved` is true for the current query — the clearest signal the
  // save actually landed.
  await expect(saveButton).toHaveCount(0);

  // Poll now lives in this page's Browse jobs header (Release A). It re-runs every saved search's own
  // criteria. TaskProgress only toasts "Poll finished..." on a genuine "done" event, so this is a real
  // success assertion, not just "the button came back".
  const pollButton = page.getByRole("button", { name: "Poll now" });
  await expect(pollButton).toBeVisible();
  await pollButton.click();
  await expect(page.getByText(/poll finished/i)).toBeVisible({ timeout: 90_000 });
});
