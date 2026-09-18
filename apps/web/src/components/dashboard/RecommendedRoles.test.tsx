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
});
