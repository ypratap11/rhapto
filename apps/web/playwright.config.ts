import { defineConfig, devices } from "@playwright/test";

// Runs against the Compose stack (docker compose up -d) seeded with profile.example and the API's
// fake LLM provider — see RHAPTO_LLM_PROVIDER below. Not part of `pnpm test`; run it by hand or in
// CI where Docker is available (spec §14).
export default defineConfig({
  testDir: "./e2e",
  globalSetup: "./e2e/global-setup.ts",
  timeout: 120_000,
  expect: { timeout: 15_000 },
  retries: process.env.CI ? 1 : 0,
  workers: 1, // one profile, one database: the specs share state by design.
  use: {
    baseURL: process.env.RHAPTO_WEB_ORIGIN ?? "http://localhost:3000",
    trace: "retain-on-failure",
    ...devices["Desktop Chrome"],
  },
  reporter: [["list"], ["html", { outputFolder: ".playwright-report", open: "never" }]],
});
