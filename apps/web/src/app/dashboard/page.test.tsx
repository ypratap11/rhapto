import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/client";
import DashboardPage from "./page";

vi.mock("@/components/dashboard/WaitingBanner", () => ({ WaitingBanner: ({ count }: { count: number }) => <div>waiting:{count}</div> }));
vi.mock("@/components/dashboard/ApplicationsSection", () => ({
  ApplicationsSection: ({ rows }: { rows: unknown[] }) => <div>applications:{rows.length}</div>,
}));
vi.mock("@/components/dashboard/RecommendedShort", () => ({ RecommendedShort: () => <div>recommended</div> }));
vi.mock("@/components/dashboard/FinishSetupLine", () => ({ FinishSetupLine: () => <div>finish-setup</div> }));

type Q = { data: unknown; error: unknown; isLoading: boolean; isPaused: boolean };
let applications: Q;
let resume: Q;
let dashboard: Q;
vi.mock("@/lib/api/queries", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/queries")>()),
  useApplications: () => applications,
  useResumeDocument: () => resume,
  useDashboard: () => dashboard,
}));

const settled = (data: unknown): Q => ({ data, error: null, isLoading: false, isPaused: false });
const columns = (rows: { id: string; status: string }[]) => ({ columns: { all: rows } });
const app = (id: string, status: string) => ({ id, status });

beforeEach(() => {
  applications = settled(columns([]));
  resume = settled({ filename: "cv.docx" });
  dashboard = settled({ needs_review_count: 0, checklist: {} });
});

describe("DashboardPage", () => {
  it("shows no sections while loading", () => {
    applications = { data: undefined, error: null, isLoading: true, isPaused: false };
    render(<DashboardPage />);
    expect(screen.getByRole("heading", { level: 1, name: "Dashboard" })).toBeInTheDocument();
    expect(screen.queryByText(/^applications:/)).toBeNull();
    expect(screen.queryByText("recommended")).toBeNull();
    expect(screen.queryByText("Start with your resume")).toBeNull();
  });

  it("asks a brand-new person to upload a resume", () => {
    resume = settled(null);
    render(<DashboardPage />);
    expect(screen.getByText("Start with your resume")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Upload resume" })).toHaveAttribute("href", "/start");
    expect(screen.queryByText("recommended")).toBeNull();
    expect(screen.queryByText(/^waiting:/)).toBeNull();
  });

  it("says what will show here when there is a resume but no applications", () => {
    render(<DashboardPage />);
    expect(
      screen.getByText("Your applications will show here. After you tailor a resume and send it, mark it as applied and track replies here."),
    ).toBeInTheDocument();
    expect(screen.queryByText(/^applications:/)).toBeNull();
    expect(screen.getByText("recommended")).toBeInTheDocument();
  });

  it("does not count discovered or queued jobs as applications", () => {
    applications = settled(columns([app("1", "discovered"), app("2", "queued")]));
    render(<DashboardPage />);
    expect(screen.queryByText(/^applications:/)).toBeNull();
  });

  it("passes only real applications to the section", () => {
    applications = settled(columns([app("1", "discovered"), app("2", "applied"), app("3", "closed")]));
    render(<DashboardPage />);
    expect(screen.getByText("applications:2")).toBeInTheDocument();
  });

  it("still shows applications from the older flow when there is no resume", () => {
    resume = settled(null);
    applications = settled(columns([app("1", "applied")]));
    render(<DashboardPage />);
    expect(screen.getByText("applications:1")).toBeInTheDocument();
    expect(screen.queryByText("Start with your resume")).toBeNull();
  });

  it("passes the waiting count to the banner", () => {
    dashboard = settled({ needs_review_count: 2, checklist: {} });
    const { unmount } = render(<DashboardPage />);
    expect(screen.getByText("waiting:2")).toBeInTheDocument();
    unmount();
    dashboard = settled({ needs_review_count: 0, checklist: {} });
    render(<DashboardPage />);
    expect(screen.getByText("waiting:0")).toBeInTheDocument();
  });

  it("shows the one finish-setup line", () => {
    render(<DashboardPage />);
    expect(screen.getByText("finish-setup")).toBeInTheDocument();
  });

  it("shows the error banner and keeps the sections when a query fails", () => {
    applications = { data: columns([app("1", "applied")]), error: new ApiError(500, null, "Server error"), isLoading: false, isPaused: false };
    render(<DashboardPage />);
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByText("applications:1")).toBeInTheDocument();
    expect(screen.getByText("recommended")).toBeInTheDocument();
  });

  it("does not call a paused query an empty one", () => {
    resume = settled(null);
    applications = { data: undefined, error: null, isLoading: false, isPaused: true };
    render(<DashboardPage />);
    expect(screen.queryByText("Start with your resume")).toBeNull();
    expect(screen.getByRole("alert")).toHaveTextContent(/can.t reach rhapto.s api/i);
  });
});
