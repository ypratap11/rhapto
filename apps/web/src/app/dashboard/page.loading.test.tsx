import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import DashboardPage from "./page";

// Intent kept from the old file: while a query is still in flight the page must not claim the person
// has nothing (no "Start with your resume", no empty-applications line) and must not show an error.
// The real child components stay mounted where they need no data of their own.
vi.mock("@/components/dashboard/RecommendedShort", () => ({ RecommendedShort: () => <div>recommended</div> }));
vi.mock("@/lib/coach/useStartTailor", () => ({ useStartTailor: () => ({ start: vi.fn(), pickedId: null, error: null, failedJobId: null }) }));

type Q = { data: unknown; error: unknown; isLoading: boolean; isPaused: boolean };
let applications: Q;
let resume: Q;
const pending: Q = { data: undefined, error: null, isLoading: true, isPaused: false };
vi.mock("@/lib/api/queries", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/queries")>()),
  useApplications: () => applications,
  useResumeDocument: () => resume,
  useDashboard: () => pending,
  useAnswers: () => pending,
  useTracks: () => pending,
  useRecommendedJobs: () => ({ ...pending, data: [] }),
  usePackageList: () => pending,
}));

describe("DashboardPage loading state", () => {
  it("shows a skeleton, no empty-state copy and no error, while applications load", () => {
    applications = { data: undefined, error: null, isLoading: true, isPaused: false };
    resume = { data: undefined, error: null, isLoading: false, isPaused: false };
    render(<DashboardPage />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Dashboard");
    expect(screen.queryByText("Start with your resume")).toBeNull();
    expect(screen.queryByText(/your applications will show here/i)).toBeNull();
    expect(screen.queryByText("recommended")).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("shows no empty-state copy while the resume loads", () => {
    applications = { data: { columns: {} }, error: null, isLoading: false, isPaused: false };
    resume = { data: undefined, error: null, isLoading: true, isPaused: false };
    render(<DashboardPage />);
    expect(screen.queryByText("Start with your resume")).toBeNull();
    expect(screen.queryByText(/your applications will show here/i)).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("does not say the person has nothing when the call settled into an error", () => {
    applications = { data: undefined, error: new Error("boom"), isLoading: false, isPaused: false };
    resume = { data: null, error: null, isLoading: false, isPaused: false };
    render(<DashboardPage />);
    expect(screen.queryByText("Start with your resume")).toBeNull();
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });

  it("holds the summary and the next step back while the dashboard loads, rather than showing guesses", () => {
    applications = { data: { columns: {} }, error: null, isLoading: false, isPaused: false };
    resume = { data: { filename: "cv.docx" }, error: null, isLoading: false, isPaused: false };
    render(<DashboardPage />);
    expect(screen.queryByText("Here's where your search stands.")).toBeNull();
    expect(screen.queryByText(/Tailor a resume for|Review your|Follow up with/)).toBeNull();
    expect(document.querySelectorAll('[data-slot="skeleton"]').length).toBeGreaterThan(0);
  });
});
