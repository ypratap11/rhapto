import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { DashboardHero } from "./DashboardHero";

// PollNowButton (rendered when either count is nonzero) calls usePollNow, a useMutation hook that
// needs a QueryClientProvider this test doesn't set up — mocked the same way PollNowButton's own
// test does, so DashboardHero can be rendered bare.
vi.mock("@/lib/api/queries", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/queries")>()),
  usePollNow: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

describe("DashboardHero", () => {
  it("reports the user's own two numbers with the review and poll actions", () => {
    render(<DashboardHero newFitCount={3} needsReviewCount={2} />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("3 new roles fit you this week · 2 resumes waiting for review");
    expect(screen.getByRole("link", { name: /review resumes/i })).toHaveAttribute("href", "/resumes?tab=review");
    expect(screen.getByRole("button", { name: /poll now/i })).toBeInTheDocument();
  });

  it("uses singular wording for one of each", () => {
    render(<DashboardHero newFitCount={1} needsReviewCount={1} />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("1 new role fits you this week · 1 resume waiting for review");
  });

  it("offers a way forward when both numbers are zero", () => {
    render(<DashboardHero newFitCount={0} needsReviewCount={0} />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Nothing new yet. Add a search or a company to your watchlist.");
    expect(screen.getByRole("link", { name: /new search/i })).toHaveAttribute("href", "/jobs");
    expect(screen.getByRole("link", { name: /add company/i })).toHaveAttribute("href", "/profile?card=watchlist");
    expect(screen.queryByRole("link", { name: /review resumes/i })).toBeNull();
  });
});
