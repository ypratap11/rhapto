import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { JobOut } from "@/lib/api/queries";
import JobsPage, { BROWSE_PAGE_SIZE } from "./page";

vi.mock("@/components/jobs/NotInterestedButton", () => ({ NotInterestedButton: () => <button>Not interested</button> }));

const run = vi.fn();
const saveSearch = vi.fn().mockResolvedValue({ id: "s1", name: "pm" });
const jobsQuery = vi.fn();
// A faithful-enough stand-in for the App Router: `push`/`replace` both update the "current URL",
// same as the real router, so the page's `useSearchParams()` reads the value a navigation just wrote
// — this is what lets `currentPage` (page.tsx) be derived straight from `searchParams` instead of
// mirrored into local state, and still be exercised by a click in these tests.
let currentSearch = new URLSearchParams();
function navigateTo(url: string) {
  currentSearch = new URLSearchParams(url.split("?")[1] ?? "");
}
const routerReplace = vi.fn(navigateTo);
const routerPush = vi.fn(navigateTo);
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: routerReplace, push: routerPush }),
  useSearchParams: () => currentSearch,
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
  currentSearch = new URLSearchParams();
  routerReplace.mockClear();
  routerPush.mockClear();
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

    it("returns to page 1 when the sort changes while on page 2 (a Select, not a toggle)", async () => {
      jobsQuery.mockReturnValue({ data: manyJobs, isLoading: false, error: null });
      const user = userEvent.setup({ delay: null });
      render(<JobsPage />);
      await user.click(screen.getByRole("button", { name: "Next" }));
      expect(screen.getByText("Page 2 of 2")).toBeInTheDocument();

      // "Newest" is the default sort now, so picking it again would be a no-op change (and
      // wouldn't exercise the reset-to-page-1 behaviour this test is about). "Fit" is a genuine
      // change from the default.
      await user.click(screen.getByLabelText("Sort"));
      await user.click(await screen.findByRole("option", { name: "Fit" }));

      expect(screen.getByText("Page 1 of 2")).toBeInTheDocument();
      expect(screen.getAllByRole("article")).toHaveLength(BROWSE_PAGE_SIZE);
    });

    it("returns to page 1 when the query changes while on page 2 (a text input, not a toggle)", async () => {
      jobsQuery.mockReturnValue({ data: manyJobs, isLoading: false, error: null });
      const user = userEvent.setup({ delay: null });
      render(<JobsPage />);
      await user.click(screen.getByRole("button", { name: "Next" }));
      expect(screen.getByText("Page 2 of 2")).toBeInTheDocument();

      await user.type(screen.getByLabelText("Title"), "p");

      expect(screen.getByText("Page 1 of 2")).toBeInTheDocument();
      expect(screen.getAllByRole("article")).toHaveLength(BROWSE_PAGE_SIZE);
    });

    it("pushes a history entry for a page step, so Back can undo it one page at a time", async () => {
      jobsQuery.mockReturnValue({ data: manyJobs, isLoading: false, error: null });
      const user = userEvent.setup({ delay: null });
      render(<JobsPage />);

      await user.click(screen.getByRole("button", { name: "Next" }));

      expect(routerPush).toHaveBeenCalledWith(expect.stringContaining("page=1"));
      expect(routerReplace).not.toHaveBeenCalled();
    });

    it("replaces (does not push) for a filter change, so Back isn't cluttered by every keystroke", async () => {
      jobsQuery.mockReturnValue({ data: manyJobs, isLoading: false, error: null });
      const user = userEvent.setup({ delay: null });
      render(<JobsPage />);

      await user.click(screen.getByRole("switch", { name: /show hidden/i }));

      expect(routerReplace).toHaveBeenCalledWith(expect.stringContaining("hidden=true"));
      expect(routerPush).not.toHaveBeenCalled();
    });

    it("clamps a stale page from the URL to the last real page instead of slicing past the end", () => {
      currentSearch = new URLSearchParams("page=99");
      jobsQuery.mockReturnValue({ data: manyJobs, isLoading: false, error: null });
      render(<JobsPage />);

      expect(screen.getByText("Page 2 of 2")).toBeInTheDocument();
      expect(screen.getAllByRole("article")).toHaveLength(6);
    });

    it("fills the last page completely when the result count divides evenly by the page size", async () => {
      const evenJobs = Array.from({ length: BROWSE_PAGE_SIZE * 2 }, (_, i) => job(`e${i}`));
      jobsQuery.mockReturnValue({ data: evenJobs, isLoading: false, error: null });
      const user = userEvent.setup({ delay: null });
      render(<JobsPage />);
      expect(screen.getByText("Page 1 of 2")).toBeInTheDocument();

      await user.click(screen.getByRole("button", { name: "Next" }));

      expect(screen.getByText("Page 2 of 2")).toBeInTheDocument();
      expect(screen.getAllByRole("article")).toHaveLength(BROWSE_PAGE_SIZE);
      expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
    });
  });

  describe("when the API is unreachable or fails", () => {
    it("shows the error banner and swaps the empty-state copy when a failed browse query has nothing cached", () => {
      jobsQuery.mockReturnValue({ data: undefined, isLoading: false, error: new Error("boom"), isPaused: false });
      render(<JobsPage />);
      expect(screen.getByRole("alert")).toBeInTheDocument();
      expect(screen.getByText(/couldn.t load jobs/i)).toBeInTheDocument();
      expect(screen.queryByText(/no jobs yet/i)).not.toBeInTheDocument();
    });

    it("shows the error banner when a browse query pauses instead of settling into an error", () => {
      // TanStack Query v5's default networkMode "online": an unreachable browse query parks at
      // fetchStatus "paused" rather than settling into `error` -- isLoading false, error null,
      // data undefined, the same shape a genuinely empty result set has.
      jobsQuery.mockReturnValue({ data: undefined, isLoading: false, error: null, isPaused: true });
      render(<JobsPage />);
      expect(screen.getByRole("alert")).toBeInTheDocument();
      expect(screen.getByText(/couldn.t load jobs/i)).toBeInTheDocument();
      expect(screen.queryByText(/no jobs yet/i)).not.toBeInTheDocument();
    });

    it("keeps showing cached jobs, with the error banner above them, when a background refetch settles into an error", () => {
      jobsQuery.mockReturnValue({ data: [job("cached")], isLoading: false, error: new Error("boom"), isPaused: false });
      render(<JobsPage />);
      expect(screen.getByRole("alert")).toBeInTheDocument();
      expect(screen.getAllByRole("article")).toHaveLength(1);
      expect(screen.queryByText(/couldn.t load jobs/i)).not.toBeInTheDocument();
    });

    it("keeps showing cached jobs, with the error banner above them, when a background refetch pauses instead", () => {
      jobsQuery.mockReturnValue({ data: [job("cached")], isLoading: false, error: null, isPaused: true });
      render(<JobsPage />);
      expect(screen.getByRole("alert")).toBeInTheDocument();
      expect(screen.getAllByRole("article")).toHaveLength(1);
      expect(screen.queryByText(/couldn.t load jobs/i)).not.toBeInTheDocument();
    });
  });
});
