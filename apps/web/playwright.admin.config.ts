import { defineConfig } from "@playwright/test";
import { ADMIN_ASSERTION, NON_ADMIN_ASSERTION } from "./e2e/fixtures/admin-assertions";

// The Compose e2e stack runs token mode, where /admin is a 404 by design, so the admin specs run
// against a built copy of this app in access mode (NEXT_PUBLIC_API_URL empty) in front of a small
// Node stub standing in for the API. Origin only: no Cloudflare is involved, so nothing here says
// anything about the hosted signed-out 302 (delivery-checklist.md covers that).
const WEB_PORT = 3107;
const STUB_PORT = 8107;

export default defineConfig({
  testDir: "./e2e",
  testMatch: /admin-phone\.spec\.ts/,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  workers: 1,
  use: { baseURL: `http://127.0.0.1:${WEB_PORT}` },
  projects: [
    {
      name: "admin-phone",
      use: { viewport: { width: 375, height: 812 }, hasTouch: true, extraHTTPHeaders: { "Cf-Access-Jwt-Assertion": ADMIN_ASSERTION } },
    },
    {
      name: "admin-desktop",
      use: { viewport: { width: 1280, height: 800 }, extraHTTPHeaders: { "Cf-Access-Jwt-Assertion": ADMIN_ASSERTION } },
    },
    // No assertion at all: what a request that skipped Cloudflare would look like.
    { name: "no-assertion", use: { viewport: { width: 1280, height: 800 } } },
    // A signed-in person who is not the owner.
    {
      name: "non-admin",
      use: { viewport: { width: 1280, height: 800 }, extraHTTPHeaders: { "Cf-Access-Jwt-Assertion": NON_ADMIN_ASSERTION } },
    },
  ],
  webServer: [
    {
      command: "node e2e/fixtures/admin-stub-server.mjs",
      url: `http://127.0.0.1:${STUB_PORT}/healthz`,
      env: { ADMIN_STUB_PORT: String(STUB_PORT) },
      reuseExistingServer: false,
    },
    {
      command: `pnpm exec next build && pnpm exec next start -H 127.0.0.1 -p ${WEB_PORT}`,
      url: `http://127.0.0.1:${WEB_PORT}/`,
      timeout: 300_000,
      env: { NEXT_PUBLIC_API_URL: "", RHAPTO_API_INTERNAL_URL: `http://127.0.0.1:${STUB_PORT}` },
      reuseExistingServer: false,
    },
  ],
  reporter: [["list"]],
});
