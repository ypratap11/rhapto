import path from "node:path";
import { expect, test, type Page } from "@playwright/test";

const SHOTS = path.resolve(__dirname, "../../../../marketing/admin-preview");
const USER_ID = "00000000-0000-4000-8000-000000000001";

async function openOverview(page: Page) {
  await page.goto("/admin");
  await expect(page.getByRole("heading", { name: "Admin", exact: true })).toBeVisible();
  await expect(page.getByTestId("value-signups")).toBeVisible();
  await expect(page.getByRole("link", { name: "ana.fictional@example.com" })).toBeVisible();
}

const noPageScroll = (page: Page) =>
  page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth);

test.describe("admin layout", () => {
  test.beforeEach(({}, testInfo) => {
    test.skip(!testInfo.project.name.startsWith("admin-"), "admin projects only");
  });

  test("no horizontal page scroll", async ({ page }) => {
    await openOverview(page);
    expect(await noPageScroll(page)).toBe(true);
    await page.goto(`/admin/users/${USER_ID}`);
    await expect(page.getByRole("button", { name: "Block user" })).toBeVisible();
    expect(await noPageScroll(page)).toBe(true);
  });

  test("every control is at least 44px tall", async ({ page }) => {
    await openOverview(page);
    const small = async () =>
      page.locator("main").evaluate((main) =>
        [...main.querySelectorAll<HTMLElement>("a[href], button, input, select, textarea, [role=button]")]
          .filter((el) => el.offsetParent !== null || getComputedStyle(el).position === "fixed")
          .map((el) => ({
            text: (el.textContent || el.getAttribute("aria-label") || el.tagName).trim().slice(0, 40),
            h: Math.round(el.getBoundingClientRect().height),
          }))
          .filter((c) => c.h < 44),
      );
    expect(await small()).toEqual([]);
    await page.goto(`/admin/users/${USER_ID}`);
    await expect(page.getByRole("button", { name: "Block user" })).toBeVisible();
    expect(await small()).toEqual([]);
  });

  test("tables scroll inside their wrapper not the page", async ({ page }) => {
    await openOverview(page);
    const wrapper = page.locator("main table").first().locator("xpath=..");
    expect(await wrapper.evaluate((el) => getComputedStyle(el).overflowX)).toMatch(/auto|scroll/);
    expect(await noPageScroll(page)).toBe(true);
    const box = await wrapper.boundingBox();
    expect(box!.x + box!.width).toBeLessThanOrEqual(page.viewportSize()!.width);
  });

  test("alert text is not clipped", async ({ page }) => {
    await openOverview(page);
    const items = page.locator("main ul li");
    await expect(items).toHaveCount(5);
    const width = page.viewportSize()!.width;
    for (const li of await items.all()) {
      const box = (await li.boundingBox())!;
      expect(box.x).toBeGreaterThanOrEqual(0);
      expect(box.x + box.width).toBeLessThanOrEqual(width);
      const clipped = await li.evaluate((el) =>
        [...el.querySelectorAll<HTMLElement>("p")].some((p) => p.scrollWidth > p.clientWidth + 1),
      );
      expect(clipped).toBe(false);
    }
  });

  test("user panel is reachable by tapping a row", async ({ page }) => {
    await openOverview(page);
    await page.getByRole("link", { name: "ana.fictional@example.com" }).click();
    await expect(page).toHaveURL(new RegExp(`/admin/users/${USER_ID}$`));
    await expect(page.getByRole("button", { name: "Reset free runs" })).toBeVisible();
    await expect(page.getByText("Why it failed")).toBeVisible();
  });

  test("overview and user page screenshots", async ({ page }, testInfo) => {
    // The phone shot is 390 wide (a current phone); the checks above use the 375 project width.
    const phone = testInfo.project.name === "admin-phone";
    if (phone) await page.setViewportSize({ width: 390, height: 844 });
    const tag = phone ? "phone" : "desktop";
    await openOverview(page);
    expect(await noPageScroll(page)).toBe(true);
    await page.screenshot({ path: path.join(SHOTS, `overview-${tag}.png`), fullPage: true });
    await page.goto(`/admin/users/${USER_ID}`);
    await expect(page.getByRole("button", { name: "Block user" })).toBeVisible();
    expect(await noPageScroll(page)).toBe(true);
    await page.screenshot({ path: path.join(SHOTS, `user-${tag}.png`), fullPage: true });
  });

  test("at desktop width the tiles sit in one row", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== "admin-desktop", "desktop only");
    await openOverview(page);
    const tops = await page
      .locator("[data-testid^=value-]")
      .evaluateAll((els) => els.map((el) => Math.round(el.getBoundingClientRect().top)));
    expect(tops).toHaveLength(5);
    expect(new Set(tops).size).toBe(1);
  });
});

test.describe("origin answers", () => {
  test("origin answers HTTP 404 with no or non-admin assertion", async ({ page }, testInfo) => {
    test.skip(!["no-assertion", "non-admin"].includes(testInfo.project.name), "non-admin projects only");
    // The real HTTP status of the document request, not what the page shows.
    const response = await page.goto("/admin");
    expect(response!.status()).toBe(404);
    const deeper = await page.goto(`/admin/users/${USER_ID}`);
    expect(deeper!.status()).toBe(404);
  });
});
