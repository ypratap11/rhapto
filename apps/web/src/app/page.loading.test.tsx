import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/client";
import DashboardPage from "./page";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));

// RecommendedRoles and ActiveApplications are unrelated to the loading-vs-empty distinction this
// file exists to catch, and pull in their own hooks (useRecommendedJobs, useApplications,
// usePackageList) — stubbed out so DashboardHero, ProfileChecklist and SavedSearchesRail can stay
// real. `page.test.tsx` mocks those three too, which is exactly why it couldn't have caught this
// class of bug: their text never rendered, so a page that fed them a loading result indistinguishable
// from a real empty one would still pass.
vi.mock("@/components/dashboard/RecommendedRoles", () => ({ RecommendedRoles: () => <div>Recommended roles</div> }));
vi.mock("@/components/dashboard/ActiveApplications", () => ({ ActiveApplications: () => <div>Active applications</div> }));

let dashboardResult: { data: unknown; error: unknown; isLoading: boolean };
vi.mock("@/lib/api/queries", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/queries")>()),
  useDashboard: () => dashboardResult,
  useTracks: () => ({ data: [] }),
  useTaxonomy: () => ({ data: { fields: [] } }),
  usePollNow: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

const fullChecklist = {
  resume_template: true,
  contact_answers: true,
  tracks: true,
  blocks_verified: true,
  guardrails: true,
  location_preferences: true,
  verified_blocks: 1,
  total_blocks: 1,
};

describe("DashboardPage loading state (real DashboardHero, ProfileChecklist, SavedSearchesRail)", () => {
  it("shows a loading skeleton on every dashboard-fed panel, not the false empty-state copy, while the call is in flight", () => {
    dashboardResult = { data: undefined, error: null, isLoading: true };
    render(<DashboardPage />);

    expect(screen.queryByText(/nothing new yet/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/save a search from the jobs page/i)).not.toBeInTheDocument();
    expect(screen.getByTestId("dashboard-hero-skeleton")).toBeInTheDocument();
    expect(screen.getByTestId("checklist-skeleton")).toBeInTheDocument();
    expect(screen.getByTestId("saved-searches-skeleton")).toBeInTheDocument();
  });

  it("shows the real empty-state copy once the call settles with genuinely nothing to report", () => {
    dashboardResult = {
      data: { new_fit_count: 0, needs_review_count: 0, checklist: fullChecklist, due_followups: [], saved_searches: [] },
      error: null,
      isLoading: false,
    };
    render(<DashboardPage />);

    expect(screen.getByText(/nothing new yet/i)).toBeInTheDocument();
    expect(screen.getByText(/save a search from the jobs page/i)).toBeInTheDocument();
    expect(screen.queryByTestId("dashboard-hero-skeleton")).not.toBeInTheDocument();
    expect(screen.queryByTestId("checklist-skeleton")).not.toBeInTheDocument();
    expect(screen.queryByTestId("saved-searches-skeleton")).not.toBeInTheDocument();
  });

  it("says the dashboard failed to load on every dashboard-fed panel, not the false empty-state copy, once the call settles into an error", () => {
    // TanStack Query v5: isLoading is isPending && isFetching, so once a failed request settles,
    // isLoading goes back to false with data still undefined — the exact state that, before this
    // fix, fell through to newFitCount ?? 0 / saved_searches ?? [] / checklist ?? null and rendered
    // the same "you have nothing" copy as a real empty dashboard.
    dashboardResult = { data: undefined, error: new ApiError(500, null, "Server error"), isLoading: false };
    render(<DashboardPage />);

    expect(screen.queryByText(/nothing new yet/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/save a search from the jobs page/i)).not.toBeInTheDocument();
    expect(screen.getByTestId("dashboard-hero-error")).toBeInTheDocument();
    expect(screen.getByTestId("checklist-error")).toBeInTheDocument();
    expect(screen.getByTestId("saved-searches-error")).toBeInTheDocument();
  });
});
