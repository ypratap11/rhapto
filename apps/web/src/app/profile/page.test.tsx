import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

const searchParams = { current: new URLSearchParams() };
vi.mock("next/navigation", () => ({
  useSearchParams: () => searchParams.current,
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
  it("shows the name, location and blocks-verified tally in the sand band", () => {
    searchParams.current = new URLSearchParams();
    render(<ProfilePage />);
    const band = screen.getByTestId("hero-band");
    expect(band.className).toContain("bg-band-sand");
    expect(within(band).getByRole("heading", { level: 1, name: "Maya Chen" })).toBeInTheDocument();
    expect(within(band).getByText(/Denver, CO/)).toBeInTheDocument();
    expect(within(band).getByText(/18 of 23 blocks verified/)).toBeInTheDocument();
  });

  it("lays out the eight summary cards in the two documented columns", () => {
    searchParams.current = new URLSearchParams();
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
    searchParams.current = new URLSearchParams("card=tracks");
    render(<ProfilePage />);
    expect(screen.getByText("Tracks content")).toBeInTheDocument();
    expect(screen.queryByText("Guardrails content")).not.toBeInTheDocument();
  });

  it("opens the Guardrails sheet when its Edit button is clicked", async () => {
    searchParams.current = new URLSearchParams();
    const user = userEvent.setup({ delay: null });
    render(<ProfilePage />);
    expect(screen.queryByText("Guardrails content")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Edit Guardrails" }));
    expect(screen.getByText("Guardrails content")).toBeInTheDocument();
  });

  it("shows a skeleton, not the fallback name, while the band's queries are loading", () => {
    searchParams.current = new URLSearchParams();
    state.answers = { data: undefined, isLoading: true, error: null, isPaused: false };
    render(<ProfilePage />);
    expect(screen.queryByRole("heading", { level: 1 })).not.toBeInTheDocument();
    state.answers = ok(answersData);
  });

  it("keeps a cached name on screen, with a note, when a background refetch is paused", () => {
    searchParams.current = new URLSearchParams();
    state.answers = { data: answersData, isLoading: false, error: null, isPaused: true };
    render(<ProfilePage />);
    expect(screen.getByRole("heading", { level: 1, name: "Maya Chen" })).toBeInTheDocument();
    expect(screen.getByRole("alert")).toBeInTheDocument();
    state.answers = ok(answersData);
  });
});
