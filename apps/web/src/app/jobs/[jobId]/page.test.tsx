import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/client";
import type { ApplicationOut, JobOut, PackageOut, PackageSummary } from "@/lib/api/queries";
import JobPage from "./page";

const routerPush = vi.fn();
vi.mock("next/navigation", () => ({
  useParams: () => ({ jobId: "j1" }),
  useRouter: () => ({ push: routerPush }),
}));

// These have their own dedicated test files (TailorButton.test.tsx, NotInterestedButton.test.tsx,
// DidYouApplyPrompt.test.tsx) and pull in hooks (useTracks/useMe/useResumeDocument/useTailor,
// useHideJob/useUnhideJob, useMarkApplied/useArchivePackage/useHideJob) unrelated to what this file
// verifies: the job page's own state-driven wiring. Stubbed to a recognizable marker instead.
vi.mock("@/components/jobs/TailorButton", () => ({ TailorButton: () => <button type="button">Tailor</button> }));
vi.mock("@/components/jobs/NotInterestedButton", () => ({ NotInterestedButton: () => <button type="button">Not interested</button> }));
vi.mock("@/components/jobs/DidYouApplyPrompt", () => ({ DidYouApplyPrompt: () => <div data-testid="did-you-apply-prompt" /> }));

type JobResult = { data: JobOut | undefined; error: unknown; isLoading: boolean; isPaused?: boolean };
type PackagesResult = { data: PackageSummary[] | undefined; error: unknown; isLoading: boolean };
type ApplicationsResult = { data: { columns: Record<string, ApplicationOut[]> } | undefined; error: unknown; isLoading: boolean };
type PackageResult = { data: PackageOut | undefined; error: unknown; isLoading: boolean };

let jobResult: JobResult = { data: undefined, error: null, isLoading: true };
let packagesResult: PackagesResult = { data: [], error: null, isLoading: false };
let applicationsResult: ApplicationsResult = { data: { columns: {} }, error: null, isLoading: false };
// What the page page's own usePackage(latest?.id ?? "", blocked) call would see if it were live:
// data only when the caller enabled the fetch, exactly like the real hook's `enabled` option.
let packageResult: PackageResult = { data: undefined, error: null, isLoading: false };
const usePackageSpy = vi.fn<(id: string, enabled: boolean) => void>();

vi.mock("@/lib/api/queries", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/queries")>()),
  useJob: () => jobResult,
  usePackages: () => packagesResult,
  useApplications: () => applicationsResult,
  useTracks: () => ({ data: [] }),
  usePackage: (id: string, enabled = true) => {
    usePackageSpy(id, enabled);
    // Mirrors TanStack's `enabled: false` behaviour: no data comes back, regardless of what a
    // test staged in `packageResult` — this is what makes a regression in the page's own
    // `enabled: blocked` gating (page.tsx's conditional usePackage fetch) show up as a failure
    // rather than passing by accident.
    return enabled ? packageResult : { data: undefined, error: null, isLoading: false };
  },
}));

beforeEach(() => {
  packageResult = { data: undefined, error: null, isLoading: false };
  usePackageSpy.mockClear();
  routerPush.mockClear();
});

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

function pkgOut(over: Partial<PackageOut> = {}): PackageOut {
  return {
    id: "p1",
    job_id: "j1",
    version: 1,
    status: "blocked",
    mode: "tune",
    track_id: "enterprise-tpm",
    llm_calls: 1,
    created_at: "2026-09-10T00:00:00Z",
    cover_note: "",
    change_log: "",
    has_pdf: false,
    has_docx: false,
    answers: {},
    parent_package_id: null,
    jd_extract: {},
    resume: { header: { name: "Maya Chen", links: [] }, summary: [], sections: [] },
    guardrail_report: {
      passed: false,
      rules_run: ["no-invented-entities"],
      violations: [{ rule: "no-invented-entities", severity: "error", message: "invented a company name", path: "summary[0]", block_id: null }],
    },
    edits: [],
    source_document: null,
    ...over,
  } as unknown as PackageOut;
}

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
    // A draft package isn't blocked, so the page must not enable the guardrail-panel fetch for it.
    expect(usePackageSpy).toHaveBeenCalledWith("p1", false);
    expect(screen.queryByText("Guardrails")).not.toBeInTheDocument();
  });

  it("offers Fix guardrails and renders the guardrail panel when the latest package is blocked", () => {
    jobResult = { data: job({ latest_package: pkg({ id: "p1", version: 1, status: "blocked" }) }), error: null, isLoading: false };
    packageResult = { data: pkgOut({ id: "p1", status: "blocked" }), error: null, isLoading: false };
    render(<JobPage />);
    expect(screen.getByRole("link", { name: "Fix guardrails" })).toHaveAttribute("href", "/jobs/j1/packages/p1");
    expect(usePackageSpy).toHaveBeenCalledWith("p1", true);
    expect(screen.getByText("Guardrails")).toBeInTheDocument();
    expect(screen.getByText(/invented a company name/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Apply" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Review" })).not.toBeInTheDocument();
  });

  it("deep-links to the specific violation clicked in the guardrail panel, not just the package", async () => {
    jobResult = { data: job({ latest_package: pkg({ id: "p1", version: 1, status: "blocked" }) }), error: null, isLoading: false };
    packageResult = { data: pkgOut({ id: "p1", status: "blocked" }), error: null, isLoading: false };
    render(<JobPage />);
    const user = userEvent.setup({ delay: null });
    await user.click(screen.getByText(/invented a company name/i));
    // "summary[0]" is pkgOut()'s violation path above -- on a blocked package the job page's whole
    // purpose is "here is what to fix", so the specific violation clicked must carry through to
    // the review page, not just the package as a whole.
    expect(routerPush).toHaveBeenCalledWith("/jobs/j1/packages/p1?path=summary%5B0%5D");
  });

  it("links a completeness row, which names no node, to the package page", () => {
    jobResult = { data: job({ latest_package: pkg({ id: "p1", version: 1, status: "blocked" }) }), error: null, isLoading: false };
    packageResult = {
      data: pkgOut({
        id: "p1",
        status: "blocked",
        guardrail_report: {
          passed: false,
          rules_run: ["completeness"],
          violations: [
            { rule: "completeness", severity: "error", message: "role block 'role-e' was selected but does not appear in Experience", path: "selection.block_ids['role-e']", block_id: "role-e" },
          ],
        },
      } as Partial<PackageOut>),
      error: null,
      isLoading: false,
    };
    render(<JobPage />);
    expect(screen.getByRole("link", { name: /does not appear in Experience/i })).toHaveAttribute("href", "/jobs/j1/packages/p1");
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
