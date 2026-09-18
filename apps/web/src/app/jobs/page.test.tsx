import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { JobOut } from "@/lib/api/queries";
import JobsPage, { BROWSE_PAGE_SIZE } from "./page";

vi.mock("@/components/jobs/NotInterestedButton", () => ({ NotInterestedButton: () => <button>Not interested</button> }));

const run = vi.fn();
const saveSearch = vi.fn().mockResolvedValue({ id: "s1", name: "pm" });
const routerReplace = vi.fn();
const jobsQuery = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: routerReplace, push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => "/jobs",
}));
vi.mock("@/lib/api/queries", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/queries")>()),
  useLiveSearch: () => ({ run, jobs: [], perSource: null, status: "idle", error: null }),
  useJobsQuery: () => jobsQuery(),
  useTracks: () => ({ data: [{ id: "t1", name: "Data PM", min_fit: 60 }] }),
  useTaxonomy: () => ({ data: { fields: [{ id: "engineering", name: "Engineering", roles: [] }] } }),
  useSourceSettings: () => ({ data: [{ source: "themuse", label: "The Muse", enabled: true, needs_key: false, key_set: false }] }),
  useSavedSearches: () => ({ data: [] }),
  useSaveSearch: () => ({ mutateAsync: saveSearch, isPending: false }),
}));

function job(id: string): JobOut {
  return {
    id,
    source: "themuse",
    company: "ExampleCo",
    title: `Role ${id}`,
    location: null,
    url: null,
    jd_text: "Do the work.",
    extracted: null,
    discovered_at: "2026-09-01T00:00:00Z",
    posted_at: "2026-09-01T00:00:00Z",
    latest_package: null,
    application_status: null,
    best_fit: 80,
    best_track_id: null,
    bucket: "fit",
    location_tier: null,
    rescued: false,
    repost_of: null,
    scores: [],
    hidden_at: null,
    unlisted_at: null,
    salary_text: null,
    search_name: null,
  } as unknown as JobOut;
}

beforeEach(() => {
  jobsQuery.mockReturnValue({ data: [], isLoading: false, error: null });
});

describe("Jobs page", () => {
  it("puts the search form in a mint band and runs a live search", async () => {
    const user = userEvent.setup({ delay: null });
    render(<JobsPage />);
    expect(screen.getByTestId("hero-band").className).toContain("bg-band-mint");
    await user.type(screen.getByLabelText("Title"), "pm");
    await user.click(screen.getByRole("button", { name: "Search" }));
    expect(run).toHaveBeenCalledWith(expect.objectContaining({ query: "pm" }));
  });

  it("offers sort, Show hidden and Save this search", async () => {
    const user = userEvent.setup({ delay: null });
    render(<JobsPage />);
    expect(screen.getByLabelText("Sort")).toBeInTheDocument();
    expect(screen.getByRole("switch", { name: /show hidden/i })).toBeInTheDocument();
    await user.type(screen.getByLabelText("Title"), "pm");
    await user.click(screen.getByRole("button", { name: /save this search/i }));
    expect(saveSearch).toHaveBeenCalledWith(expect.objectContaining({ query: "pm" }));
  });

  it("says the grid is empty rather than showing nothing", () => {
    render(<JobsPage />);
    expect(screen.getByText(/no jobs yet/i)).toBeInTheDocument();
  });

  describe("Browse paging", () => {
    const manyJobs = Array.from({ length: BROWSE_PAGE_SIZE + 6 }, (_, i) => job(`j${i}`));

    it("shows only one page of cards and labels it, with Previous disabled on page 1", () => {
      jobsQuery.mockReturnValue({ data: manyJobs, isLoading: false, error: null });
      render(<JobsPage />);
      expect(screen.getAllByRole("article")).toHaveLength(BROWSE_PAGE_SIZE);
      expect(screen.getByText("Page 1 of 2")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();
      expect(screen.getByRole("button", { name: "Next" })).not.toBeDisabled();
    });

    it("advances to the next slice and disables Next on the last page", async () => {
      jobsQuery.mockReturnValue({ data: manyJobs, isLoading: false, error: null });
      const user = userEvent.setup({ delay: null });
      render(<JobsPage />);
      await user.click(screen.getByRole("button", { name: "Next" }));
      expect(screen.getAllByRole("article")).toHaveLength(6);
      expect(screen.getByText("Page 2 of 2")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
      expect(screen.getByRole("button", { name: "Previous" })).not.toBeDisabled();
    });

    it("hides the pager entirely when everything fits on one page", () => {
      jobsQuery.mockReturnValue({ data: [job("solo")], isLoading: false, error: null });
      render(<JobsPage />);
      expect(screen.queryByText(/page \d+ of \d+/i)).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Next" })).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Previous" })).not.toBeInTheDocument();
    });

    it("returns to page 1 when a filter changes while on page 2", async () => {
      jobsQuery.mockReturnValue({ data: manyJobs, isLoading: false, error: null });
      const user = userEvent.setup({ delay: null });
      render(<JobsPage />);
      await user.click(screen.getByRole("button", { name: "Next" }));
      expect(screen.getByText("Page 2 of 2")).toBeInTheDocument();

      await user.click(screen.getByRole("switch", { name: /show hidden/i }));

      expect(screen.getByText("Page 1 of 2")).toBeInTheDocument();
      expect(screen.getAllByRole("article")).toHaveLength(BROWSE_PAGE_SIZE);
    });
  });
});
