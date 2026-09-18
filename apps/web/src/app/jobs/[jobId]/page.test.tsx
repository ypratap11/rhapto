import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/client";
import type { ApplicationOut, JobOut, PackageSummary } from "@/lib/api/queries";
import JobPage from "./page";

vi.mock("next/navigation", () => ({
  useParams: () => ({ jobId: "j1" }),
  useRouter: () => ({ push: vi.fn() }),
}));

// These have their own dedicated test files (TailorButton.test.tsx, NotInterestedButton.test.tsx,
// DidYouApplyPrompt.test.tsx) and pull in hooks (useTracks/useMe/useResumeDocument/useTailor,
// useHideJob/useUnhideJob, useMarkApplied/useArchivePackage/useHideJob) unrelated to what this file
// verifies: the job page's own state-driven wiring. Stubbed to a recognizable marker instead.
vi.mock("@/components/queue/TailorButton", () => ({ TailorButton: () => <button type="button">Tailor</button> }));
vi.mock("@/components/jobs/NotInterestedButton", () => ({ NotInterestedButton: () => <button type="button">Not interested</button> }));
vi.mock("@/components/jobs/DidYouApplyPrompt", () => ({ DidYouApplyPrompt: () => <div data-testid="did-you-apply-prompt" /> }));

type JobResult = { data: JobOut | undefined; error: unknown; isLoading: boolean; isPaused?: boolean };
type PackagesResult = { data: PackageSummary[] | undefined; error: unknown; isLoading: boolean };
type ApplicationsResult = { data: { columns: Record<string, ApplicationOut[]> } | undefined; error: unknown; isLoading: boolean };

let jobResult: JobResult = { data: undefined, error: null, isLoading: true };
let packagesResult: PackagesResult = { data: [], error: null, isLoading: false };
let applicationsResult: ApplicationsResult = { data: { columns: {} }, error: null, isLoading: false };

vi.mock("@/lib/api/queries", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/queries")>()),
  useJob: () => jobResult,
  usePackages: () => packagesResult,
  useApplications: () => applicationsResult,
  useTracks: () => ({ data: [] }),
  // The job page calls this unconditionally (Rules of Hooks) but only the blocked-package branch,
  // which no test here exercises, ever reads its data.
  usePackage: () => ({ data: undefined, error: null, isLoading: false }),
}));

function job(over: Partial<JobOut> = {}): JobOut {
  return {
    application_status: null,
    best_fit: 80,
    best_track_id: null,
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
    search_name: null,
    source: "greenhouse",
    title: "TPM",
    unlisted_at: null,
    url: "https://boards.example.com/j1",
    ...over,
  } as JobOut;
}

function application(over: Partial<ApplicationOut> & { job: ApplicationOut["job"] }): ApplicationOut {
  return {
    applied_at: null,
    closed_reason: null,
    created_at: "2026-09-01T00:00:00Z",
    follow_up_at: null,
    id: "a1",
    notes: "",
    package_id: null,
    status: "applied",
    status_history: [],
    updated_at: "2026-09-01T00:00:00Z",
    ...over,
  };
}

const pkg = (over: Partial<PackageSummary> = {}): PackageSummary => ({ id: "p1", version: 1, status: "draft", mode: "tune", created_at: "2026-09-10T00:00:00Z", ...over });

describe("JobPage", () => {
  it("shows a shape-matched skeleton while loading, not an empty or error state", () => {
    jobResult = { data: undefined, error: null, isLoading: true };
    render(<JobPage />);
    expect(document.querySelectorAll('[data-slot="skeleton"]').length).toBeGreaterThan(0);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.queryByText(/doesn't exist/i)).not.toBeInTheDocument();
  });

  it("shows a not-found state, not the generic error banner, for a deleted or mistyped job id", () => {
    jobResult = { data: undefined, error: new ApiError(404, null, "Not Found"), isLoading: false };
    render(<JobPage />);
    expect(screen.getByText(/this job doesn't exist/i)).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /back to jobs/i })).toHaveAttribute("href", "/jobs");
  });

  it("shows only an error banner when the API is unreachable and nothing is cached", () => {
    // TanStack's networkMode: "online" parks an unreachable query at isLoading: false, error: null —
    // isPaused is the only signal, and this is the state that goes missing without it.
    jobResult = { data: undefined, error: null, isLoading: false, isPaused: true };
    render(<JobPage />);
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { level: 1 })).not.toBeInTheDocument();
  });

  it("keeps showing cached content alongside a banner when a background refetch fails", () => {
    jobResult = { data: job(), error: new ApiError(500, null, "Server error"), isLoading: false };
    render(<JobPage />);
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "TPM", level: 1 })).toBeInTheDocument();
  });

  it("sets the breadcrumb and document title to Jobs › company · title", () => {
    jobResult = { data: job(), error: null, isLoading: false };
    render(<JobPage />);
    expect(screen.getByText("ExampleCo · TPM")).toBeInTheDocument();
    expect(document.title).toBe("Jobs › ExampleCo · TPM");
  });

  it("offers Tailor when the job has no package", () => {
    jobResult = { data: job({ latest_package: null }), error: null, isLoading: false };
    render(<JobPage />);
    expect(screen.getByRole("button", { name: "Tailor" })).toBeInTheDocument();
  });

  it("offers Review when the latest package needs review", () => {
    jobResult = { data: job({ latest_package: pkg({ id: "p1", version: 1, status: "draft" }) }), error: null, isLoading: false };
    render(<JobPage />);
    expect(screen.getByRole("link", { name: "Review" })).toHaveAttribute("href", "/jobs/j1/packages/p1");
  });

  it("offers Apply, and mounts the Did-you-apply prompt, when the latest package is ready", () => {
    jobResult = { data: job({ latest_package: pkg({ id: "p2", version: 2, status: "ready" }) }), error: null, isLoading: false };
    render(<JobPage />);
    expect(screen.getByRole("button", { name: "Apply" })).toBeInTheDocument();
    expect(screen.getByTestId("did-you-apply-prompt")).toBeInTheDocument();
  });

  it("shows an Applied status pill instead of an action once an application exists", () => {
    jobResult = { data: job({ latest_package: pkg({ id: "p2", version: 2, status: "ready" }) }), error: null, isLoading: false };
    applicationsResult = { data: { columns: { applied: [application({ id: "a1", status: "applied", job: { id: "j1", company: "ExampleCo", title: "TPM" } })] } }, error: null, isLoading: false };
    render(<JobPage />);
    expect(screen.getByText("Applied")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Apply" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Pipeline" })).toBeInTheDocument();
  });

  it("shows the Reposted notice with a link to reuse the original's newest resume", () => {
    jobResult = { data: job({ repost_of: "j0" }), error: null, isLoading: false };
    packagesResult = {
      data: [pkg({ id: "p8", version: 1 }), pkg({ id: "p9", version: 2 })],
      error: null,
      isLoading: false,
    };
    render(<JobPage />);
    expect(screen.getByRole("link", { name: /reuse resume v2/i })).toHaveAttribute("href", "/jobs/j0/packages/p9");
    expect(screen.getByRole("link", { name: /see the original posting/i })).toHaveAttribute("href", "/jobs/j0");
  });
});
