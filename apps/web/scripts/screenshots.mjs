#!/usr/bin/env node
// Screenshot walkthrough for the user guide (Task 13 references these images by filename). Run it
// by hand after starting the app:
//
//   1. From the repo root:      docker compose up -d
//   2. From apps/web:           pnpm dev
//   3. First time only:         npx playwright install chromium
//   4. From apps/web:           pnpm screenshots
//
// Captures every portal route (spec §3), once in light and once in dark, to
// docs/user-guide/images/ — these ARE committed, unlike e2e/'s test-results/ and
// .playwright-report/. That is why this script is stricter than a scratch tool: see the two
// guards below.
//
// There is no /login page: the web app gates on a bearer token stored in localStorage (see
// components/shell/TokenGate.tsx). Rather than fill in the Settings form by hand, each browser
// context gets the token and API URL seeded into localStorage before the app's first script runs
// (`context.addInitScript`), the same keys `src/lib/api/client.ts` reads (`rhapto.token`,
// `rhapto.apiUrl`) and the same one the theme toggle uses (`rhapto.theme`, see
// components/ui/theme-toggle.tsx). The token comes from RHAPTO_API_TOKEN in the repo root's
// .env — it is read into memory only, never logged, and never written to a file this script
// creates.
import { chromium } from "playwright";
import { mkdir } from "node:fs/promises";
import { existsSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const WEB_DIR = resolve(HERE, "..");
const REPO_ROOT = resolve(WEB_DIR, "../..");
// Output goes into the user guide, not a scratch folder: these are the images §15 illustrates.
const OUT_DIR = resolve(REPO_ROOT, "docs/user-guide/images");

/** Minimal .env reader: KEY=VALUE lines, no interpolation, no quoting rules — matches this repo's .env. */
function readEnvFile(path) {
  if (!existsSync(path)) return {};
  const env = {};
  for (const line of readFileSync(path, "utf8").split("\n")) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const eq = trimmed.indexOf("=");
    if (eq === -1) continue;
    env[trimmed.slice(0, eq).trim()] = trimmed.slice(eq + 1).trim();
  }
  return env;
}

const env = readEnvFile(resolve(REPO_ROOT, ".env"));
const TOKEN = process.env.RHAPTO_API_TOKEN || env.RHAPTO_API_TOKEN || "";
const API_URL = process.env.RHAPTO_PUBLIC_API_URL || env.RHAPTO_PUBLIC_API_URL || "http://localhost:8000";
const WEB_URL = process.env.RHAPTO_WEB_ORIGIN || env.RHAPTO_WEB_ORIGIN || "http://localhost:3000";
const EXPECTED_EMAIL = env.RHAPTO_USER_EMAIL || "";

if (!TOKEN) {
  console.error("RHAPTO_API_TOKEN is empty in the root .env — set it before running this script.");
  process.exit(1);
}

/** Guard #1: never point this script at a real profile. The images below are committed, so a
 * mismatch here (this instance's account email doesn't match .env's RHAPTO_USER_EMAIL, i.e. this
 * is not profile.example) must stop the run before anything is captured, not just warn. */
async function assertExampleProfile() {
  const res = await fetch(`${API_URL}/api/v1/me`, { headers: { Authorization: `Bearer ${TOKEN}` } });
  if (!res.ok) {
    console.error(`GET ${API_URL}/api/v1/me -> ${res.status}. Is the stack up (docker compose up -d)?`);
    process.exit(1);
  }
  const me = await res.json();
  if (!EXPECTED_EMAIL) {
    console.error("RHAPTO_USER_EMAIL is not set in the root .env — cannot confirm this is profile.example. Refusing to run.");
    process.exit(1);
  }
  if (me.email !== EXPECTED_EMAIL) {
    console.error(
      `GET /api/v1/me returned ${JSON.stringify(me.email)}, expected ${JSON.stringify(EXPECTED_EMAIL)} (.env's RHAPTO_USER_EMAIL). ` +
        "Refusing to screenshot what might be a real profile — re-import profile.example first (see e2e/global-setup.ts).",
    );
    process.exit(1);
  }
}

/** The portal's routes (spec §3). The two nested pages are found by href pattern rather than
 * hard-coded ids, so the walkthrough works against any seeded database. */
const PAGES = [
  { name: "dashboard", path: "/" },
  { name: "jobs", path: "/jobs" },
  { name: "resumes", path: "/resumes" },
  { name: "pipeline", path: "/pipeline" },
  { name: "profile", path: "/profile" },
  { name: "settings", path: "/settings" },
];

/** Seeds the same localStorage keys Settings writes, before any page script runs. */
async function seededContext(browser, theme) {
  const context = await browser.newContext();
  await context.addInitScript(
    ({ token, apiUrl, theme }) => {
      window.localStorage.setItem("rhapto.token", token);
      window.localStorage.setItem("rhapto.apiUrl", apiUrl);
      window.localStorage.setItem("rhapto.theme", theme);
    },
    { token: TOKEN, apiUrl: API_URL, theme },
  );
  return context;
}

/** The first href matching `pattern` anywhere on `path`. */
async function findHref(page, path, pattern) {
  await page.goto(`${WEB_URL}${path}`, { waitUntil: "networkidle" });
  await settle(page);
  // `page.$$eval` is Playwright's selector-evaluation API (runs the callback against matched DOM
  // nodes inside the browser page) — not the JS `eval()` global, and not code-injection-prone here
  // since the callback is this fixed inline function, not a runtime-built string.
  const hrefs = await page.$$eval("a[href]", (as) => as.map((a) => a.getAttribute("href")));
  return hrefs.find((href) => href && pattern.test(href)) ?? null;
}

/** `waitUntil: "networkidle"` fires on the *initial* document load, which on this SPA can settle
 * before React hydrates and TanStack Query's own client-side fetches even start — a screenshot
 * taken right then catches skeleton placeholders instead of real content. Wait for the loading
 * markers each data-driven panel renders (JobGrid, DashboardHero, ProfileChecklist,
 * SavedSearchesRail) to clear, capped so a page with none of them (e.g. Settings) doesn't stall. */
const SKELETON_SELECTOR = [
  '[data-slot="job-grid-skeleton"]',
  '[data-testid="dashboard-hero-skeleton"]',
  '[data-testid="checklist-skeleton"]',
  '[data-testid="saved-searches-skeleton"]',
].join(", ");

async function settle(page) {
  await page
    .waitForSelector(SKELETON_SELECTOR, { state: "detached", timeout: 8_000 })
    .catch(() => undefined);
  // Layout/paint settle for whatever just swapped in.
  await page.waitForTimeout(300);
}

async function capture(page, name, theme) {
  await settle(page);
  const path = resolve(OUT_DIR, `${name}-${theme}.png`);
  await page.screenshot({ path, fullPage: true });
  return path;
}

async function run() {
  await assertExampleProfile();
  await mkdir(OUT_DIR, { recursive: true });
  const browser = await chromium.launch();
  const saved = [];

  for (const theme of ["light", "dark"]) {
    const context = await seededContext(browser, theme);
    const page = await context.newPage();

    for (const { name, path } of PAGES) {
      await page.goto(`${WEB_URL}${path}`, { waitUntil: "networkidle" });
      // Guard #2: the Settings page's Bearer token field defaults to type="password" (masked) —
      // this script must never toggle its "Show" button, so it never does anything on this page
      // but navigate and capture.
      saved.push(await capture(page, name, theme));
    }

    const jobPath = await findHref(page, "/jobs", /^\/jobs\/[^/]+$/);
    if (jobPath) {
      await page.goto(`${WEB_URL}${jobPath}`, { waitUntil: "networkidle" });
      saved.push(await capture(page, "job", theme));
    } else {
      console.warn(`No job to open — skipping the job screenshot (${theme}).`);
    }

    // /resumes defaults to the "review" (draft) tab, which is exactly what should be reviewable —
    // never "blocked" or "applied", where an older, possibly non-fictional package could live.
    const reviewPath = await findHref(page, "/resumes", /^\/jobs\/.+\/packages\/.+/);
    if (reviewPath) {
      await page.goto(`${WEB_URL}${reviewPath}`, { waitUntil: "networkidle" });
      saved.push(await capture(page, "review", theme));
    } else {
      console.warn(`No package to review yet — skipping the review screenshot (${theme}).`);
    }

    await context.close();
  }

  await browser.close();
  console.log(`Saved ${saved.length} screenshot(s) to ${OUT_DIR}`);
  for (const path of saved) console.log(` - ${path}`);
}

run().catch((err) => {
  console.error(err);
  process.exit(1);
});
