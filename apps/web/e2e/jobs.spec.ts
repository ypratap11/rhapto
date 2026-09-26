import { expect, test } from "./fixtures";

const QUERY = "engineer";

test("Search fills the grid with scored jobs, and Save this search surfaces on the dashboard rail", async ({ page }) => {
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

  await page.goto("/dashboard");
  const pollButton = page.getByRole("button", { name: "Poll now" });
  await expect(pollButton).toBeVisible();
  await pollButton.click();
  // Poll now (worker/tasks.py poll_now) re-runs every saved search's own criteria and, unlike the
  // ad hoc live search above, tags newly-discovered postings with this search's id — that
  // attribution is what makes "N new" possible at all. TaskProgress only toasts "Poll finished…"
  // on a genuine "done" event, so this is a real success assertion, not just "the button came
  // back" (which a `poll_now` that failed after doing its work — see worker/tasks.py's
  // `poll_now` and its JSON-safe "done" publish — would also produce).
  await expect(page.getByText(/poll finished/i)).toBeVisible({ timeout: 90_000 });

  // SavedSearchesRail is not invalidated when a poll finishes (only tailoring is — see
  // TaskProgress.tsx), so a fresh load is the only way to see its updated count.
  await page.reload();
  const rail = page.getByRole("region", { name: "Saved searches" });
  const savedLink = rail.getByRole("link", { name: QUERY, exact: true });
  await expect(savedLink).toBeVisible();

  // A count only appears once the poll actually discovers postings this search hadn't tagged yet
  // (jobs already known from a previous run of this same query are not re-tagged — see
  // db/repositories/searches.py's new_counts). Rather than assert a specific number that depends
  // on the live state of external job boards, this asks the API for the ground truth and checks
  // the rail agrees with it exactly, in either direction.
  const apiUrl = process.env.RHAPTO_PUBLIC_API_URL ?? "http://localhost:8000";
  const token = process.env.RHAPTO_API_TOKEN ?? "";
  const searchesRes = await fetch(`${apiUrl}/api/v1/searches`, { headers: { Authorization: `Bearer ${token}` } });
  expect(searchesRes.ok).toBe(true);
  const searches = (await searchesRes.json()) as { name: string; new_count: number }[];
  const saved = searches.find((s) => s.name === QUERY);
  expect(saved, `no saved search named ${JSON.stringify(QUERY)} on the API`).toBeTruthy();
  if (saved && saved.new_count > 0) {
    await expect(savedLink).toContainText(`${saved.new_count} new`);
  } else {
    await expect(savedLink).not.toContainText("new");
  }
});
