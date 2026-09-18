import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useEffect, useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

// A faithful-enough App Router stand-in (mirrors src/app/jobs/page.test.tsx): `push` updates the
// "current URL" and notifies subscribers, so `useSearchParams()` re-renders the page the same way
// Next's real router does on navigation. This is what lets `openCard` (page.tsx) be derived
// straight from `searchParams` — not mirrored into local state — and still be exercised by a click
// in these tests: real round-tripping, not just a value read once on mount.
const { getSearchParams, setSearchParams, subscribeSearchParams, routerPush, routerReplace } = vi.hoisted(() => {
  let params = new URLSearchParams();
  const listeners = new Set<() => void>();
  function setSearchParams(next: URLSearchParams) {
    params = next;
    listeners.forEach((l) => l());
  }
  return {
    getSearchParams: () => params,
    setSearchParams,
    subscribeSearchParams: (l: () => void) => {
      listeners.add(l);
      return () => {
        listeners.delete(l);
      };
    },
    routerPush: vi.fn((url: string) => setSearchParams(new URLSearchParams(url.split("?")[1] ?? ""))),
    routerReplace: vi.fn((url: string) => setSearchParams(new URLSearchParams(url.split("?")[1] ?? ""))),
  };
});

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: routerPush, replace: routerReplace }),
  useSearchParams: () => {
    const [, forceRender] = useState(0);
    useEffect(() => subscribeSearchParams(() => forceRender((n) => n + 1)), []);
    return getSearchParams();
  },
}));

vi.mock("@/components/profile/ResumeDocumentTab", () => ({ ResumeDocumentTab: () => <div>Resume template content</div> }));
vi.mock("@/components/profile/TracksTab", () => ({ TracksTab: () => <div>Tracks content</div> }));
vi.mock("@/components/profile/BlocksTab", () => ({ BlocksTab: () => <div>Blocks content</div> }));
vi.mock("@/components/profile/BasesTab", () => ({ BasesTab: () => <div>Bases content</div> }));
vi.mock("@/components/profile/AnswersTab", () => ({ AnswersTab: () => <div>Answers content</div> }));
vi.mock("@/components/profile/GuardrailsTab", () => ({ GuardrailsTab: () => <div>Guardrails content</div> }));
vi.mock("@/components/profile/WatchlistTab", () => ({ WatchlistTab: () => <div>Watchlist content</div> }));

type QueryState<T> = { data: T | undefined; isLoading: boolean; error: unknown; isPaused: boolean };
function ok<T>(data: T): QueryState<T> {
  return { data, isLoading: false, error: null, isPaused: false };
}

const checklist = {
  resume_template: true,
  contact_answers: true,
  tracks: true,
  blocks_verified: true,
  guardrails: true,
  location_preferences: true,
  verified_blocks: 18,
  total_blocks: 23,
};

// Fictional fixture (profile.example/answers.yaml) — never data from profile/.
const answersData = { name: "Maya Chen", location_home: "Denver, CO", location_preferred: "Denver, CO, Boulder, CO", remote_ok: "yes" };

const state = {
  answers: ok(answersData),
  dashboard: ok({ new_fit_count: 0, needs_review_count: 0, checklist, due_followups: [], saved_searches: [] }),
  tracks: ok([{ id: "pm", name: "Program Manager", min_fit: 60 }]),
  bases: ok([{ id: "default", name: "Default", block_ids: [], section_order: [], style: {} }]),
  guardrails: ok([{ rule: "no-unverified-metrics", active: true, config: {} }]),
  watchlist: ok([{ company: "Acme", source: "greenhouse" as const, board: "acme", keywords: [], discovered: false }]),
  resumeDocument: ok(null),
};

vi.mock("@/lib/api/queries", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/queries")>()),
  useAnswers: () => state.answers,
  useDashboard: () => state.dashboard,
  useTracks: () => state.tracks,
  useBases: () => state.bases,
  useGuardrails: () => state.guardrails,
  useWatchlist: () => state.watchlist,
  useResumeDocument: () => state.resumeDocument,
}));

import ProfilePage from "./page";

describe("ProfilePage", () => {
  beforeEach(() => {
    routerPush.mockClear();
    routerReplace.mockClear();
  });

  it("shows the name, location and blocks-verified tally in the sand band", () => {
    setSearchParams(new URLSearchParams());
    render(<ProfilePage />);
    const band = screen.getByTestId("hero-band");
    expect(band.className).toContain("bg-band-sand");
    expect(within(band).getByRole("heading", { level: 1, name: "Maya Chen" })).toBeInTheDocument();
    expect(within(band).getByText(/Denver, CO/)).toBeInTheDocument();
    expect(within(band).getByText(/18 of 23 blocks verified/)).toBeInTheDocument();
  });

  it("lays out the eight summary cards in the two documented columns", () => {
    setSearchParams(new URLSearchParams());
    render(<ProfilePage />);
    const cards = document.querySelectorAll("[data-card-id]");
    expect(Array.from(cards).map((c) => c.getAttribute("data-card-id"))).toEqual([
      "resume-template",
      "tracks",
      "blocks",
      "bases",
      "answers",
      "guardrails",
      "location",
      "watchlist",
    ]);
    // First four (resume-template..bases) share one column container, the rest another.
    const leftColumn = cards[0]?.parentElement;
    const rightColumn = cards[4]?.parentElement;
    expect(leftColumn).not.toBe(rightColumn);
    expect(leftColumn?.children).toHaveLength(4);
    expect(rightColumn?.children).toHaveLength(4);
  });

  it("opens the Tracks sheet on load when the URL says ?card=tracks", () => {
    setSearchParams(new URLSearchParams("card=tracks"));
    render(<ProfilePage />);
    expect(screen.getByText("Tracks content")).toBeInTheDocument();
    expect(screen.queryByText("Guardrails content")).not.toBeInTheDocument();
  });

  it("opens the Guardrails sheet when its Edit button is clicked", async () => {
    setSearchParams(new URLSearchParams());
    const user = userEvent.setup({ delay: null });
    render(<ProfilePage />);
    expect(screen.queryByText("Guardrails content")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Edit Guardrails" }));
    expect(screen.getByText("Guardrails content")).toBeInTheDocument();
  });

  it("round-trips through the URL on open and close, so ?card= is a real, shareable, Back-able address", async () => {
    setSearchParams(new URLSearchParams());
    const user = userEvent.setup({ delay: null });
    render(<ProfilePage />);

    // Opening pushes ?card=guardrails — a link to it is shareable, and it is a distinct history
    // entry a Back can undo (mirrors src/app/jobs/page.tsx's goToPage, which also pushes).
    await user.click(screen.getByRole("button", { name: "Edit Guardrails" }));
    expect(routerPush).toHaveBeenLastCalledWith("/profile?card=guardrails");
    expect(getSearchParams().get("card")).toBe("guardrails");

    // Closing removes it from the URL again — via `replace`, not `push` (see the next test): a
    // close is the undo of an open, not a fresh step.
    await user.click(screen.getByRole("button", { name: "Close" }));
    expect(getSearchParams().get("card")).toBeNull();
    expect(screen.queryByText("Guardrails content")).not.toBeInTheDocument();
  });

  it("pushes to open a sheet but replaces to close it, so Back after closing leaves the page instead of reopening it", async () => {
    setSearchParams(new URLSearchParams());
    const user = userEvent.setup({ delay: null });
    render(<ProfilePage />);

    await user.click(screen.getByRole("button", { name: "Edit Guardrails" }));
    expect(routerPush).toHaveBeenCalledWith("/profile?card=guardrails");
    expect(routerReplace).not.toHaveBeenCalled();

    routerPush.mockClear();
    await user.click(screen.getByRole("button", { name: "Close" }));
    // Pushing here (the bug this test pins) would leave a `?card=guardrails` entry in history that
    // one Back would land back on, reopening the very sheet the user just dismissed.
    expect(routerPush).not.toHaveBeenCalled();
    expect(routerReplace).toHaveBeenCalledWith("/profile");
  });

  it("closes an open sheet on browser Back, since openCard is derived from the URL, not latched", () => {
    setSearchParams(new URLSearchParams("card=guardrails"));
    render(<ProfilePage />);
    expect(screen.getByText("Guardrails content")).toBeInTheDocument();

    // A real Back doesn't call this page's own push — it changes the URL out from under it, the
    // same way the mocked router does here. The page must react to that, not just to its own calls.
    act(() => setSearchParams(new URLSearchParams()));
    expect(screen.queryByText("Guardrails content")).not.toBeInTheDocument();
  });

  it("shows a skeleton, not the fallback name, while the band's queries are loading", () => {
    setSearchParams(new URLSearchParams());
    state.answers = { data: undefined, isLoading: true, error: null, isPaused: false };
    render(<ProfilePage />);
    expect(screen.queryByRole("heading", { level: 1 })).not.toBeInTheDocument();
    state.answers = ok(answersData);
  });

  it("keeps a cached name on screen, with a note, when a background refetch is paused", () => {
    setSearchParams(new URLSearchParams());
    state.answers = { data: answersData, isLoading: false, error: null, isPaused: true };
    render(<ProfilePage />);
    expect(screen.getByRole("heading", { level: 1, name: "Maya Chen" })).toBeInTheDocument();
    expect(screen.getByRole("alert")).toBeInTheDocument();
    state.answers = ok(answersData);
  });
});
