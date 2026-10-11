import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { PackageListItem } from "@/lib/api/queries";

const searchParams = { current: new URLSearchParams() };
const replace = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
  useSearchParams: () => searchParams.current,
}));

type ListState = { data: PackageListItem[] | undefined; isLoading: boolean; error: unknown; isPaused: boolean };
const listState = { current: { data: [], isLoading: false, error: null, isPaused: false } as ListState };

const anyState = { current: { data: undefined as PackageListItem[] | undefined } };

vi.mock("@/lib/api/queries", () => ({
  usePackageList: () => listState.current,
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
  it("has one h1 'My resumes', no breadcrumb, and the three tabs in order with no Applied tab", () => {
    searchParams.current = new URLSearchParams();
    listState.current = { data: [], isLoading: false, error: null, isPaused: false };
    render(<ResumesPage />);
    expect(screen.getAllByRole("heading", { level: 1 }).map((h) => h.textContent)).toEqual(["My resumes"]);
    expect(screen.queryByRole("navigation", { name: /breadcrumb/i })).not.toBeInTheDocument();
    expect(screen.getAllByRole("tab").map((t) => t.textContent)).toEqual(["To review", "Ready to send", "Needs attention"]);
  });

  it("selects the tab named in ?tab=", () => {
    searchParams.current = new URLSearchParams("tab=blocked");
    listState.current = { data: [], isLoading: false, error: null, isPaused: false };
    render(<ResumesPage />);
    expect(screen.getByRole("tab", { name: /needs attention/i })).toHaveAttribute("aria-selected", "true");
  });

  it("falls back to review for the legacy ?filter=all value", () => {
    searchParams.current = new URLSearchParams("filter=all");
    listState.current = { data: [], isLoading: false, error: null, isPaused: false };
    render(<ResumesPage />);
    expect(screen.getByRole("tab", { name: /to review/i })).toHaveAttribute("aria-selected", "true");
  });

  it("an empty tab, when other resumes exist, says 'Nothing here right now.'", () => {
    searchParams.current = new URLSearchParams("tab=ready");
    listState.current = { data: [], isLoading: false, error: null, isPaused: false };
    anyState.current = { data: [blockedRow] };
    render(<ResumesPage />);
    expect(screen.getByText("Nothing here right now.")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "+ Tailor a resume" })).not.toBeInTheDocument();
  });

  it("with no resumes at all it invites the first one and links to /start", () => {
    searchParams.current = new URLSearchParams();
    listState.current = { data: [], isLoading: false, error: null, isPaused: false };
    anyState.current = { data: [] };
    render(<ResumesPage />);
    expect(screen.getByText("No resumes yet. Pick a job and Rhapto tailors your resume to it.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "+ Tailor a resume" })).toHaveAttribute("href", "/start");
  });

  it("shows a table skeleton while the list is loading, not the empty state", () => {
    searchParams.current = new URLSearchParams();
    listState.current = { data: undefined, isLoading: true, error: null, isPaused: false };
    const { container } = render(<ResumesPage />);
    expect(container.querySelector('[data-slot="table-skeleton"]')).toBeInTheDocument();
    expect(screen.queryByText(/nothing here right now/i)).not.toBeInTheDocument();
  });

  it("a blocked row links to the review page so its violations can be fixed", () => {
    searchParams.current = new URLSearchParams("tab=blocked");
    listState.current = { data: [blockedRow], isLoading: false, error: null, isPaused: false };
    render(<ResumesPage />);
    const link = screen.getByRole("link", { name: /BlockedCo.*Needs attention/ });
    expect(link).toHaveAttribute("href", "/jobs/j3/packages/p3");
    expect(link).toHaveTextContent("Fix");
  });

  // A paused background refetch (TanStack's networkMode: "online" when the API is unreachable)
  // must not discard rows already on screen — same shape as src/app/dashboard/page.tsx:59-65. The banner is
  // additive, not a replacement for cached content.
  it("shows the error banner alongside cached rows when a background refetch is paused", () => {
    searchParams.current = new URLSearchParams("tab=blocked");
    listState.current = { data: [blockedRow], isLoading: false, error: null, isPaused: true };
    render(<ResumesPage />);
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByText("BlockedCo")).toBeInTheDocument();
  });
});
