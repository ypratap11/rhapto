import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ApplicationOut, JobOut } from "@/lib/api/queries";
import { JobHeader } from "./JobHeader";

let applicationsData: { columns: Record<string, ApplicationOut[]> } | undefined;
vi.mock("@/lib/api/queries", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/queries")>()),
  useApplications: () => ({ data: applicationsData }),
  useTracks: () => ({ data: [{ id: "data", name: "Data", min_fit: 60 }] }),
  useTailor: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useResumeDocument: () => ({ data: null, isPending: false }),
  useMe: () => ({ data: { user_id: "u1", email: "dev@example.com", llm_configured: true, auth_mode: "token" } }),
  useHideJob: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUnhideJob: () => ({ mutateAsync: vi.fn(), isPending: false }),
  invalidateJobs: vi.fn(),
}));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("./TaskProgress", () => ({ TaskProgress: () => null }));

function job(over: Partial<JobOut> = {}): JobOut {
  return {
    application_status: null,
    best_fit: 86,
    best_track_id: "data",
    bucket: "fit",
    company: "ExampleCo",
    discovered_at: "2026-09-01T00:00:00Z",
    extracted: null,
    id: "j1",
    jd_text: "Do the job.",
    latest_package: null,
    location: null,
    location_tier: null,
    posted_at: null,
    repost_of: null,
    rescued: false,
    salary_text: null,
    scores: [],
    search_name: "Remote data roles",
    source: "adzuna",
    title: "Analyst",
    unlisted_at: null,
    url: "https://boards.example.com/j1",
    ...over,
  } as JobOut;
}

const pkg = (status: "draft" | "ready" | "blocked") => ({ id: "p1", version: 1, status });
const track = { name: "Data", min_fit: 60 };

function renderHeader(j: JobOut, t: { name: string; min_fit: number } | null = track) {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <JobHeader job={j} track={t} />
    </QueryClientProvider>,
  );
}

/** Elements carrying the filled (default) button variant class. */
const filledCount = () => document.querySelectorAll(".bg-primary").length;

describe("JobHeader", () => {
  beforeEach(() => {
    applicationsData = { columns: {} };
  });

  it("none: offers Tailor my resume for this job as the one filled button", () => {
    renderHeader(job());
    expect(screen.getByRole("button", { name: "Tailor my resume for this job" })).toBeInTheDocument();
    expect(filledCount()).toBe(1);
  });

  it("draft: Review resume is the one filled button", () => {
    renderHeader(job({ latest_package: pkg("draft") }));
    expect(screen.getByRole("link", { name: "Review resume" })).toHaveAttribute("href", "/jobs/j1/packages/p1");
    expect(filledCount()).toBe(1);
  });

  it("blocked: Fix and review is the one filled button", () => {
    renderHeader(job({ latest_package: pkg("blocked") }));
    expect(screen.getByRole("link", { name: "Fix and review" })).toHaveAttribute("href", "/jobs/j1/packages/p1");
    expect(filledCount()).toBe(1);
  });

  it("ready with a safe posting url: Download and open the posting", () => {
    renderHeader(job({ latest_package: pkg("ready") }));
    expect(screen.getByRole("button", { name: "Download and open the posting" })).toBeInTheDocument();
    expect(filledCount()).toBe(1);
  });

  it("ready without a safe posting url: only says Download resume", () => {
    renderHeader(job({ latest_package: pkg("ready"), url: "javascript:alert(1)" }));
    expect(screen.getByRole("button", { name: "Download resume" })).toBeInTheDocument();
    expect(screen.queryByText(/open the posting/i)).not.toBeInTheDocument();
    expect(filledCount()).toBe(1);
  });

  it("ready with no url at all: Download resume", () => {
    renderHeader(job({ latest_package: pkg("ready"), url: null }));
    expect(screen.getByRole("button", { name: "Download resume" })).toBeInTheDocument();
  });

  it("applied: a status badge and an outline Dashboard link, no filled button", () => {
    applicationsData = {
      columns: {
        applied: [
          {
            id: "a1",
            status: "applied",
            job: { id: "j1", company: "ExampleCo", title: "Analyst" },
            status_history: [],
          } as unknown as ApplicationOut,
        ],
      },
    };
    renderHeader(job({ latest_package: pkg("ready") }));
    expect(screen.getByText("Applied")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Dashboard" })).toBeInTheDocument();
    expect(filledCount()).toBe(0);
  });

  it("drops the source, via and track badges", () => {
    renderHeader(job());
    expect(screen.queryByText(/adzuna/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/via /)).not.toBeInTheDocument();
    expect(screen.queryByText("Data")).not.toBeInTheDocument();
  });

  it("captions the ring with the match and the goal, only when there is a track", () => {
    const { unmount } = renderHeader(job());
    expect(screen.getByText("86% match for your Data goal")).toBeInTheDocument();
    unmount();
    renderHeader(job(), null);
    expect(screen.queryByText(/match for your/)).not.toBeInTheDocument();
  });

  it("Not interested is a ghost control with an 11-unit tap height", () => {
    renderHeader(job());
    const btn = screen.getByRole("button", { name: /not interested/i });
    expect(btn).toHaveClass("min-h-11");
    expect(btn).not.toHaveClass("bg-primary");
  });
});
