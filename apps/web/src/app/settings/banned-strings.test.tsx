import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import SettingsPage from "./page";
import { setSettings } from "@/lib/api/client";
import type { SearchOut, SourceSetting, UsageOut } from "@/lib/api/queries";

// Visible words on /settings must be plain words. Anything inside a native <details> is the
// "for the curious" corner and is exempt; everything else, including aria-labels, is checked.
const BANNED = /\.env|RHAPTO_API_TOKEN|rapidapi_key|app_key|app_id|LLM|tokens|\bpoll|\bblocks?\b|\bbases?\b|\btracks?\b|guardrails?|docs\/|database|rhapto profile/i;

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("@/lib/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/client")>();
  return {
    ...actual,
    get SAME_ORIGIN_DEPLOYMENT() {
      return false;
    },
  };
});

const zero = { calls: 0, input_tokens: 0, output_tokens: 0, cache_read_tokens: 0, cache_creation_tokens: 0, cost_usd: null, unpriced_calls: 0 };
const usage: UsageOut = {
  totals: { ...zero, calls: 4, input_tokens: 2000, output_tokens: 900, cost_usd: 0.42 },
  last_30_days: { ...zero, calls: 2, input_tokens: 1000, output_tokens: 400, cost_usd: 0.2 },
  recent: [
    { package_id: "p1", job_id: "j1", company: "ExampleCo", job_title: "Program Manager", model: "claude-sonnet-5", calls: 2, input_tokens: 1000, output_tokens: 400, cost_usd: 0.2, created_at: "2026-09-15T00:00:00Z" },
  ],
};
const sources: SourceSetting[] = [
  { id: "themuse", label: "The Muse", enabled: true, needs_key: false, key_set: false, fields: [], configured: true, paused: false, runnable: true, last_run: { started_at: "2026-09-26T12:00:00Z", finished_at: "2026-09-26T12:00:01Z", found: 5, new: 2, error: null, search_id: "s1", search_name: "Denver PM", search_location: "Denver" } },
  { id: "adzuna", label: "Adzuna", enabled: false, needs_key: true, key_set: false, fields: ["app_id", "app_key"], configured: false, paused: false, runnable: false, last_run: null },
  { id: "jsearch", label: "JSearch", enabled: true, needs_key: true, key_set: true, fields: ["rapidapi_key"], configured: true, paused: true, runnable: false, last_run: null },
];
const searches: SearchOut[] = [
  { id: "s1", name: "Denver PM", keywords: ["program", "manager"], location: "Denver", remote: "include", active: true, derived_from_track_id: "pm", new_count: 1, created_at: "2026-09-01T00:00:00Z", last_viewed_at: null, runs: 3, ever_found: false, last_run_at: "2026-09-26T00:00:00Z" },
];
const providers = [{ id: "anthropic", label: "Anthropic", models: ["claude-sonnet-5"], default: "claude-sonnet-5" }];

vi.mock("@/lib/api/queries", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/queries")>()),
  useLlmSettings: () => ({
    data: { kind: "ok", settings: { provider: "anthropic", model: "claude-sonnet-5", key_set: false, key_hint: null, source: "env", providers } },
    isLoading: false,
    error: null,
  }),
  useSaveLlmSettings: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useTestLlm: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useDeleteLlmSettings: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useSourceSettings: () => ({ data: sources, isLoading: false, error: null, isPaused: false }),
  useSaveSourceSettings: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useTestSource: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useResumeSource: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useSavedSearches: () => ({ data: searches, isLoading: false, error: null, isPaused: false }),
  useUpdateSavedSearch: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useDeleteSavedSearch: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUsageSummary: () => ({ data: usage, isLoading: false, error: null }),
}));

afterEach(() => window.localStorage.clear());

describe("Settings page vocabulary", () => {
  it("uses no technical words outside <details>, in text or aria-labels", () => {
    setSettings({ token: "tok", apiUrl: "http://localhost:8000" });
    render(
      <QueryClientProvider client={new QueryClient()}>
        <SettingsPage />
      </QueryClientProvider>,
    );
    const body = document.body.cloneNode(true) as HTMLElement;
    body.querySelectorAll("details").forEach((d) => d.remove());
    expect(body.textContent ?? "").not.toMatch(BANNED);
    const labels = Array.from(body.querySelectorAll("[aria-label]")).map((el) => el.getAttribute("aria-label") ?? "");
    for (const label of labels) expect(label).not.toMatch(BANNED);
    // Guard against a vacuous pass: the page really rendered its sections.
    expect(body.textContent).toContain("Settings");
    expect(labels.length).toBeGreaterThan(0);
  });
});
