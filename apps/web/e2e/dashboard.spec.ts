import { expect, test } from "./fixtures";

test("the dashboard reports real numbers and a recommendation reaches a resume", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toContainText(/new role|Nothing new yet/);

  // The checklist's <ul> has no accessible name of its own (it is named only by the enclosing
  // <section>'s aria-labelledby), so the section itself — exposed as role="region" once it has an
  // accessible name — is what carries "Profile checklist", not the list.
  const checklist = page.getByRole("region", { name: /profile checklist/i });
  await expect(checklist.getByRole("listitem")).toHaveCount(6);

  // Recommended roles renders first in the left column (src/app/page.tsx), so the first article on
  // the page is a recommendation, not an Active-applications card.
  const card = page.getByRole("article").first();
  const role = await card.getByRole("link").first().innerText();
  const company = await card.locator("p").first().innerText();
  await card.getByRole("link", { name: "Tailor" }).click();
  await expect(page).toHaveURL(/\/jobs\/[^/]+$/);

  // Explicit "Build from blocks": this stack's uploaded resume document (Profile > Resume
  // template) is shared across the whole suite and not reset by profile.example's import (see
  // global-setup.ts). Leaving Mode on its default would silently switch to "tune" and render that
  // document's real content on the review page below.
  await page.getByRole("combobox", { name: "Mode" }).click();
  await page.getByRole("option", { name: "Build from blocks" }).click();
  await page.getByRole("button", { name: "Tailor" }).click();
  await expect(page.getByRole("link", { name: "Review", exact: true })).toBeVisible({ timeout: 120_000 });

  await page.goto("/resumes?tab=review");
  await expect(page.getByRole("row", { name: role }).filter({ hasText: company })).toBeVisible();
});
