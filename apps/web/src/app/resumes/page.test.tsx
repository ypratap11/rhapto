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

vi.mock("@/lib/api/queries", () => ({
  usePackageList: () => listState.current,
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
};

describe("ResumesPage", () => {
  it("lists the four tabs in order", () => {
    searchParams.current = new URLSearchParams();
    listState.current = { data: [], isLoading: false, error: null, isPaused: false };
    render(<ResumesPage />);
    expect(screen.getAllByRole("tab").map((t) => t.textContent)).toEqual(["Needs review", "Ready", "Blocked", "Applied"]);
  });

  it("selects the tab named in ?tab=", () => {
    searchParams.current = new URLSearchParams("tab=blocked");
    listState.current = { data: [], isLoading: false, error: null, isPaused: false };
    render(<ResumesPage />);
    expect(screen.getByRole("tab", { name: /blocked/i })).toHaveAttribute("aria-selected", "true");
  });

  it("falls back to review for the legacy ?filter=all value", () => {
    searchParams.current = new URLSearchParams("filter=all");
    listState.current = { data: [], isLoading: false, error: null, isPaused: false };
    render(<ResumesPage />);
    expect(screen.getByRole("tab", { name: /needs review/i })).toHaveAttribute("aria-selected", "true");
  });

  it("shows a table skeleton while the list is loading, not the empty state", () => {
    searchParams.current = new URLSearchParams();
    listState.current = { data: undefined, isLoading: true, error: null, isPaused: false };
    const { container } = render(<ResumesPage />);
    expect(container.querySelector('[data-slot="table-skeleton"]')).toBeInTheDocument();
    expect(screen.queryByText(/nothing to review/i)).not.toBeInTheDocument();
  });

  it("a blocked row links to the review page so its violations can be fixed", () => {
    searchParams.current = new URLSearchParams("tab=blocked");
    listState.current = { data: [blockedRow], isLoading: false, error: null, isPaused: false };
    render(<ResumesPage />);
    expect(screen.getByRole("link", { name: /^fix$/i })).toHaveAttribute("href", "/jobs/j3/packages/p3");
  });
});
