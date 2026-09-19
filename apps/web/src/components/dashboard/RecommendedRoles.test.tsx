import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { TrackInfo } from "@/components/jobs/JobCard";
import type { JobOut } from "@/lib/api/queries";
import { RecommendedRoles } from "./RecommendedRoles";

vi.mock("@/components/jobs/NotInterestedButton", () => ({ NotInterestedButton: () => <button>Not interested</button> }));

const recommendedJobs = vi.fn();
vi.mock("@/lib/api/queries", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/queries")>()),
  useRecommendedJobs: (page: number) => recommendedJobs(page),
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

const tenJobs = Array.from({ length: 10 }, (_, i) => job(`j${i}`));
const tracks: Record<string, TrackInfo> = {};

describe("RecommendedRoles", () => {
  it("shows ten jobs per page, each with Tailor and Not interested", () => {
    recommendedJobs.mockReturnValue({ data: tenJobs, isLoading: false, error: null });
    render(<RecommendedRoles tracks={tracks} />);
    expect(recommendedJobs).toHaveBeenCalledWith(0);
    expect(screen.getAllByRole("link", { name: /tailor/i })).toHaveLength(10);
    expect(screen.getAllByText("Not interested")).toHaveLength(10);
  });

  it("stops paging at five pages", async () => {
    const user = userEvent.setup({ delay: null });
    recommendedJobs.mockReturnValue({ data: tenJobs, isLoading: false, error: null });
    render(<RecommendedRoles tracks={tracks} />);
    const next = screen.getByRole("button", { name: /^next$/i });
    for (let i = 0; i < 6; i++) {
      await user.click(next);
    }
    expect(recommendedJobs).toHaveBeenLastCalledWith(4);
    expect(next).toBeDisabled();
  });

  it("disables Previous on the first page", () => {
    recommendedJobs.mockReturnValue({ data: tenJobs, isLoading: false, error: null });
    render(<RecommendedRoles tracks={tracks} />);
    expect(screen.getByRole("button", { name: /^previous$/i })).toBeDisabled();
  });

  it("shows an empty state when there is nothing to recommend", () => {
    recommendedJobs.mockReturnValue({ data: [], isLoading: false, error: null });
    render(<RecommendedRoles tracks={tracks} />);
    expect(screen.getByText(/nothing to recommend yet/i)).toBeInTheDocument();
  });

  describe("when the API is unreachable or fails", () => {
    it("shows the error banner and swaps the empty-state copy when a failed query has nothing cached", () => {
      recommendedJobs.mockReturnValue({ data: undefined, isLoading: false, error: new Error("boom"), isPaused: false });
      render(<RecommendedRoles tracks={tracks} />);
      expect(screen.getByRole("alert")).toBeInTheDocument();
      expect(screen.getByText(/couldn.t load recommended roles/i)).toBeInTheDocument();
      expect(screen.queryByText(/nothing to recommend yet/i)).not.toBeInTheDocument();
    });

    it("shows the error banner when the query pauses instead of settling into an error", () => {
      // TanStack Query v5's default networkMode "online": an unreachable query parks at
      // fetchStatus "paused" rather than settling into `error` -- isLoading false, error null,
      // data undefined, the same shape a genuinely empty page has.
      recommendedJobs.mockReturnValue({ data: undefined, isLoading: false, error: null, isPaused: true });
      render(<RecommendedRoles tracks={tracks} />);
      expect(screen.getByRole("alert")).toBeInTheDocument();
      expect(screen.getByText(/couldn.t load recommended roles/i)).toBeInTheDocument();
      expect(screen.queryByText(/nothing to recommend yet/i)).not.toBeInTheDocument();
    });

    it("keeps showing cached jobs, with the error banner above them, when a background refetch settles into an error", () => {
      recommendedJobs.mockReturnValue({ data: tenJobs, isLoading: false, error: new Error("boom"), isPaused: false });
      render(<RecommendedRoles tracks={tracks} />);
      expect(screen.getByRole("alert")).toBeInTheDocument();
      expect(screen.getAllByRole("link", { name: /tailor/i })).toHaveLength(10);
      expect(screen.queryByText(/couldn.t load recommended roles/i)).not.toBeInTheDocument();
    });

    it("keeps showing cached jobs, with the error banner above them, when a background refetch pauses instead", () => {
      recommendedJobs.mockReturnValue({ data: tenJobs, isLoading: false, error: null, isPaused: true });
      render(<RecommendedRoles tracks={tracks} />);
      expect(screen.getByRole("alert")).toBeInTheDocument();
      expect(screen.getAllByRole("link", { name: /tailor/i })).toHaveLength(10);
      expect(screen.queryByText(/couldn.t load recommended roles/i)).not.toBeInTheDocument();
    });
  });
});
