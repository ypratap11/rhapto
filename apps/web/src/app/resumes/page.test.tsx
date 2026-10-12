import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { PackageListItem } from "@/lib/api/queries";

const searchParams = { current: new URLSearchParams() };
const replace = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
  useSearchParams: () => searchParams.current,
}));

type ListState = { data: PackageListItem[] | undefined; isLoading: boolean; error: unknown; isPaused: boolean };
const empty: ListState = { data: [], isLoading: false, error: null, isPaused: false };
// Filter-aware, like the real hook (key ["package-list", filter]): each tab has its own list.
const listState = { current: { review: empty, ready: empty, blocked: empty } as Record<"review" | "ready" | "blocked", ListState> };
const filtersAsked: string[] = [];
/** Every tab answers the same, for the tests that only care about the current one. */
const all = (state: ListState) => ({ review: state, ready: state, blocked: state });

const anyState = { current: { data: undefined as PackageListItem[] | undefined } };

vi.mock("@/lib/api/queries", () => ({
  usePackageList: (filter: "review" | "ready" | "blocked") => {
    filtersAsked.push(filter);
    return listState.current[filter];
  },
  usePackageListAny: () => anyState.current,
  useTracks: () => ({ data: [] }),
  useMarkPackageReady: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useArchivePackage: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useHideJob: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUnhideJob: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

import ResumesPage from "./page";

const blockedRow: PackageListItem = {
  id: "p3",
  job_id: "j3",
  company: "BlockedCo",
  title: "Engineer",
  best_fit: 40,
  best_track_id: null,
  status: "blocked",
  version: 1,
  mode: "blocks",
  application_status: null,
  created_at: "2026-09-01T00:00:00Z",
  // A blocked row with two error-severity violations: "blocked" alone is what this branch removes.
  violations: 2,
};

describe("ResumesPage", () => {
  it("has one h1 'My resumes', no breadcrumb, and the three status tiles in order with no Applied tab", () => {
    searchParams.current = new URLSearchParams();
    listState.current = all({ data: [], isLoading: false, error: null, isPaused: false });
    render(<ResumesPage />);
    expect(screen.getAllByRole("heading", { level: 1 }).map((h) => h.textContent)).toEqual(["My resumes"]);
    expect(screen.queryByRole("navigation", { name: /breadcrumb/i })).not.toBeInTheDocument();
    const group = screen.getByRole("group", { name: "Resume status" });
    expect(within(group).getAllByRole("button").map((b) => b.textContent)).toEqual([
      expect.stringContaining("To review"),
      expect.stringContaining("Ready to send"),
      expect.stringContaining("Needs attention"),
    ]);
    expect(screen.getByTestId("page-hero")).toContainElement(group);
    expect(screen.getByText("Every tailored resume and what it is waiting on.")).toBeInTheDocument();
  });

  it("shows each tile's own row count, and a dash while a list is loading", () => {
    searchParams.current = new URLSearchParams();
    filtersAsked.length = 0;
    listState.current = {
      review: { ...empty, data: [blockedRow, { ...blockedRow, id: "p4" }] },
      ready: { data: undefined, isLoading: true, error: null, isPaused: false },
      blocked: { ...empty, data: [] },
    };
    render(<ResumesPage />);
    expect(screen.getByRole("button", { name: /To review/ })).toHaveTextContent("2");
    expect(screen.getByRole("button", { name: /Ready to send/ })).toHaveTextContent("–");
    expect(screen.getByRole("button", { name: /Needs attention/ })).toHaveTextContent("0");
    expect(filtersAsked.slice(0, 3)).toEqual(["review", "ready", "blocked"]);
  });

  it("says it could not load a tile with no data and an error, but keeps the count of one with cached data", () => {
    searchParams.current = new URLSearchParams();
    listState.current = {
      review: { data: [blockedRow], isLoading: false, error: new Error("x"), isPaused: false },
      ready: { data: undefined, isLoading: false, error: new Error("x"), isPaused: false },
      blocked: { data: undefined, isLoading: false, error: null, isPaused: true },
    };
    render(<ResumesPage />);
    expect(screen.getByRole("button", { name: /To review/ })).toHaveTextContent("1");
    expect(screen.getByRole("button", { name: /To review/ })).not.toHaveTextContent("Couldn");
    expect(screen.getByRole("button", { name: /Ready to send/ })).toHaveTextContent("Couldn't load");
    expect(screen.getByRole("button", { name: /Needs attention/ })).toHaveTextContent("Couldn't load");
  });

  it("clicking a tile switches the tab through router.replace", async () => {
    const user = userEvent.setup({ delay: null });
    searchParams.current = new URLSearchParams();
    listState.current = all(empty);
    render(<ResumesPage />);
    replace.mockClear();
    await user.click(screen.getByRole("button", { name: /Ready to send/ }));
    expect(replace).toHaveBeenCalledWith("/resumes?tab=ready");
  });

  it("lists the current tab's rows, not another tab's", () => {
    searchParams.current = new URLSearchParams("tab=ready");
    listState.current = {
      review: { ...empty, data: [blockedRow] },
      ready: { ...empty, data: [{ ...blockedRow, id: "p9", company: "ReadyCo", status: "ready" }] },
      blocked: empty,
    };
    render(<ResumesPage />);
    expect(screen.getByText("ReadyCo")).toBeInTheDocument();
    expect(screen.queryByText("BlockedCo")).not.toBeInTheDocument();
  });

  it("selects the tab named in ?tab=", () => {
    searchParams.current = new URLSearchParams("tab=blocked");
    listState.current = all({ data: [], isLoading: false, error: null, isPaused: false });
    render(<ResumesPage />);
    expect(screen.getByRole("button", { name: /needs attention/i })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: /to review/i })).toHaveAttribute("aria-pressed", "false");
  });

  it("falls back to review for the legacy ?filter=all value", () => {
    searchParams.current = new URLSearchParams("filter=all");
    listState.current = all({ data: [], isLoading: false, error: null, isPaused: false });
    render(<ResumesPage />);
    expect(screen.getByRole("button", { name: /to review/i })).toHaveAttribute("aria-pressed", "true");
  });

  it("an empty tab, when other resumes exist, says 'Nothing here right now.'", () => {
    searchParams.current = new URLSearchParams("tab=ready");
    listState.current = all({ data: [], isLoading: false, error: null, isPaused: false });
    anyState.current = { data: [blockedRow] };
    render(<ResumesPage />);
    expect(screen.getByText("Nothing here right now.")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "+ Tailor a resume" })).not.toBeInTheDocument();
  });

  it("with no resumes at all it invites the first one and links to /start", () => {
    searchParams.current = new URLSearchParams();
    listState.current = all({ data: [], isLoading: false, error: null, isPaused: false });
    anyState.current = { data: [] };
    render(<ResumesPage />);
    expect(screen.getByText("No resumes yet. Pick a job and Rhapto tailors your resume to it.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "+ Tailor a resume" })).toHaveAttribute("href", "/start");
  });

  it("shows a table skeleton while the list is loading, not the empty state", () => {
    searchParams.current = new URLSearchParams();
    listState.current = all({ data: undefined, isLoading: true, error: null, isPaused: false });
    const { container } = render(<ResumesPage />);
    expect(container.querySelector('[data-slot="table-skeleton"]')).toBeInTheDocument();
    expect(screen.queryByText(/nothing here right now/i)).not.toBeInTheDocument();
  });

  it("a blocked row links to the review page so its violations can be fixed", () => {
    searchParams.current = new URLSearchParams("tab=blocked");
    listState.current = all({ data: [blockedRow], isLoading: false, error: null, isPaused: false });
    render(<ResumesPage />);
    const link = screen.getByRole("link", { name: /BlockedCo.*Needs attention.*Full rewrite/ });
    expect(link).toHaveAttribute("href", "/jobs/j3/packages/p3");
    expect(link).toHaveTextContent("Fix");
  });

  // A paused background refetch (TanStack's networkMode: "online" when the API is unreachable)
  // must not discard rows already on screen — same shape as src/app/dashboard/page.tsx:59-65. The banner is
  // additive, not a replacement for cached content.
  it("shows the error banner alongside cached rows when a background refetch is paused", () => {
    searchParams.current = new URLSearchParams("tab=blocked");
    listState.current = all({ data: [blockedRow], isLoading: false, error: null, isPaused: true });
    render(<ResumesPage />);
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByText("BlockedCo")).toBeInTheDocument();
  });
});
