import { render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/client";
import DashboardPage from "./page";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));

vi.mock("@/components/dashboard/DashboardHero", () => ({
  DashboardHero: ({ newFitCount, needsReviewCount }: { newFitCount: number; needsReviewCount: number }) => (
    <h1>
      hero:{newFitCount}:{needsReviewCount}
    </h1>
  ),
}));
vi.mock("@/components/dashboard/RecommendedRoles", () => ({ RecommendedRoles: ({ noTracks }: { noTracks?: boolean }) => <div>Recommended roles{noTracks ? " (no tracks)" : ""}</div> }));
vi.mock("@/components/dashboard/ActiveApplications", () => ({ ActiveApplications: () => <div>Active applications</div> }));
vi.mock("@/components/dashboard/ProfileChecklist", () => ({ ProfileChecklist: () => <div>Profile checklist</div> }));
vi.mock("@/components/dashboard/SavedSearchesRail", () => ({ SavedSearchesRail: () => <div>Saved searches rail</div> }));

let tracksResult: { data: unknown } = { data: [{ id: "t1", name: "Data PM", min_fit: 60 }] };
let dashboardResult: { data: unknown; error: unknown; isLoading: boolean } = { data: undefined, error: null, isLoading: true };
vi.mock("@/lib/api/queries", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/queries")>()),
  useDashboard: () => dashboardResult,
  useTracks: () => tracksResult,
  useTaxonomy: () => ({ data: { fields: [{ id: "engineering", name: "Engineering", roles: [] }] } }),
}));

const checklist = {
  resume_template: true,
  contact_answers: true,
  tracks: true,
  blocks_verified: true,
  guardrails: true,
  location_preferences: true,
  verified_blocks: 1,
  total_blocks: 1,
};

describe("DashboardPage", () => {
  afterEach(() => {
    tracksResult = { data: [{ id: "t1", name: "Data PM", min_fit: 60 }] };
  });

  it("puts the hero in a peach, tall band", () => {
    dashboardResult = { data: undefined, error: null, isLoading: true };
    render(<DashboardPage />);
    const band = screen.getByTestId("hero-band");
    expect(band.className).toContain("bg-band-peach");
    expect(band.className).toContain("min-h-band-tall");
  });

  it("puts the search card, Recommended roles and Active applications in the left column, and the checklist and saved-search rail in the right rail", () => {
    dashboardResult = {
      data: { new_fit_count: 3, needs_review_count: 2, checklist, due_followups: [], saved_searches: [] },
      error: null,
      isLoading: false,
    };
    render(<DashboardPage />);

    const aside = screen.getByRole("complementary");
    expect(within(aside).getByText("Profile checklist")).toBeInTheDocument();
    expect(within(aside).getByText("Saved searches rail")).toBeInTheDocument();
    expect(within(aside).queryByText(/recommended roles/i)).not.toBeInTheDocument();

    const main = aside.previousElementSibling as HTMLElement;
    expect(main).not.toBeNull();
    expect(within(main).getByRole("heading", { name: /find your next role/i })).toBeInTheDocument();
    expect(within(main).getByText("Recommended roles")).toBeInTheDocument();
    expect(within(main).getByText("Active applications")).toBeInTheDocument();
    expect(within(main).queryByText("Profile checklist")).not.toBeInTheDocument();
  });

  it("shows an ApiErrorBanner instead of a blank page when the dashboard call fails", () => {
    dashboardResult = { data: undefined, error: new ApiError(500, null, "Server error"), isLoading: false };
    render(<DashboardPage />);
    expect(screen.getByRole("alert")).toBeInTheDocument();
    // Not a blank page: the rest of the Dashboard still renders around the banner.
    expect(screen.getByRole("heading", { name: /find your next role/i })).toBeInTheDocument();
    expect(screen.getByText("Recommended roles")).toBeInTheDocument();
  });

  it("tells Recommended roles when the user has no tracks, and only when that is settled", () => {
    dashboardResult = {
      data: { new_fit_count: 0, needs_review_count: 0, checklist, due_followups: [], saved_searches: [] },
      error: null,
      isLoading: false,
    };
    tracksResult = { data: [] };
    const { unmount } = render(<DashboardPage />);
    expect(screen.getByText("Recommended roles (no tracks)")).toBeInTheDocument();
    unmount();
    tracksResult = { data: undefined }; // still loading: no verdict
    render(<DashboardPage />);
    expect(screen.getByText("Recommended roles")).toBeInTheDocument();
  });
});
