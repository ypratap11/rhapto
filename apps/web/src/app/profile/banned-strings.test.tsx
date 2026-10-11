import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { useEffect, useState } from "react";
import { describe, expect, it, vi } from "vitest";

// Visible words on /profile must be plain words. Anything inside a native <details> is exempt;
// everything else, including aria-labels, is checked. Each card is also opened so the editors
// inside the side sheets are covered, not just the summary tiles.
const BANNED = /\.env|RHAPTO_API_TOKEN|rapidapi_key|app_key|app_id|LLM|tokens|\bpoll|\bblocks?\b|\bbases?\b|\btracks?\b|guardrails?|docs\/|database|rhapto profile/i;

const { getSearchParams, setSearchParams, subscribeSearchParams } = vi.hoisted(() => {
  let params = new URLSearchParams();
  const listeners = new Set<() => void>();
  return {
    getSearchParams: () => params,
    setSearchParams: (next: URLSearchParams) => {
      params = next;
      listeners.forEach((l) => l());
    },
    subscribeSearchParams: (l: () => void) => {
      listeners.add(l);
      return () => {
        listeners.delete(l);
      };
    },
  };
});

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => {
    const [, force] = useState(0);
    useEffect(() => subscribeSearchParams(() => force((n) => n + 1)), []);
    return getSearchParams();
  },
}));

type QueryState<T> = { data: T | undefined; isLoading: boolean; error: unknown; isPaused: boolean };
function ok<T>(data: T): QueryState<T> {
  return { data, isLoading: false, error: null, isPaused: false };
}

// Fictional fixtures only.
const checklist = { resume_template: true, contact_answers: true, tracks: true, blocks_verified: true, guardrails: true, location_preferences: true, verified_blocks: 12, total_blocks: 13 };
const block = { id: "pm-1", type: "achievement", org: "ExampleCo", role: "Program Manager", period: "2020-2023", verified: true, metric: null, content: "Ran the weekly planning meeting.", tags: [], attribution: null, concurrent: false, visibility: null };

vi.mock("@/lib/api/queries", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/queries")>()),
  useAnswers: () => ok({ name: "Maya Chen", location_home: "Denver, CO", location_preferred: "Denver, CO", remote_ok: "yes" }),
  useDashboard: () => ok({ new_fit_count: 0, needs_review_count: 0, checklist, due_followups: [], saved_searches: [] }),
  useTracks: () => ok([{ id: "pm", name: "Program Manager", description: null, keywords: [], resume_base: "default", min_fit: 60 }]),
  useBases: () => ok([{ id: "default", name: "Default", block_ids: ["pm-1"], section_order: [], style: {} }]),
  useBlocks: () => ok([block]),
  useGuardrails: () => ok([{ rule: "no-invented-entities", active: true, config: {} }]),
  useWatchlist: () => ok([{ company: "Acme", source: "greenhouse", board: "acme", keywords: [], discovered: false }]),
  useSources: () => ok([{ name: "greenhouse", label: "Greenhouse", kind: "board" }]),
  useAggregators: () => ok([]),
  useResumeDocument: () => ok(null),
  useTaxonomy: () => ok({ fields: [] }),
  useTaxonomySuggestions: () => ok([]),
}));

import ProfilePage from "./page";

const CARDS = ["resume-template", "tracks", "blocks", "bases", "answers", "guardrails", "location", "watchlist"];

function assertPlain() {
  const body = document.body.cloneNode(true) as HTMLElement;
  body.querySelectorAll("details").forEach((d) => d.remove());
  expect(body.textContent ?? "").not.toMatch(BANNED);
  for (const el of Array.from(body.querySelectorAll("[aria-label]"))) expect(el.getAttribute("aria-label") ?? "").not.toMatch(BANNED);
}

function renderPage() {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <ProfilePage />
    </QueryClientProvider>,
  );
}

describe("Profile page vocabulary", () => {
  it("uses no technical words on the page itself", () => {
    setSearchParams(new URLSearchParams());
    renderPage();
    assertPlain();
    expect(document.body.textContent).toContain("Maya Chen");
  });

  it.each(CARDS)("uses no technical words with the %s card open", (card) => {
    setSearchParams(new URLSearchParams(`card=${card}`));
    renderPage();
    assertPlain();
    expect(document.querySelector('[role="dialog"]')).not.toBeNull();
  });
});
