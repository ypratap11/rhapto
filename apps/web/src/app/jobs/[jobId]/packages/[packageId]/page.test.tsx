import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { PackageOut } from "@/lib/api/queries";

vi.mock("next/navigation", () => ({
  useParams: () => ({ jobId: "j1", packageId: "pkg-1" }),
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

const tunePackage = {
  id: "pkg-1",
  job_id: "j1",
  version: 1,
  status: "blocked",
  mode: "tune",
  track_id: "platform",
  llm_calls: 1,
  input_tokens: 1200,
  output_tokens: 340,
  cache_read_tokens: 0,
  cache_creation_tokens: 0,
  llm_model: "claude-sonnet-5",
  cost_usd: 0.58,
  created_at: "2026-09-11T00:00:00Z",
  cover_note: "note",
  change_log: "log",
  has_pdf: true,
  has_docx: true,
  answers: {},
  parent_package_id: null,
  jd_extract: {},
  resume: { header: { name: "Maya Chen", links: [] }, summary: [], sections: [] },
  guardrail_report: {
    passed: false,
    rules_run: ["tune-scope"],
    violations: [{ rule: "tune-scope", severity: "error", message: "rewrote a protected line", path: "edits[0]", block_id: null }],
  },
  edits: [{ paragraph_id: "p-3", before: "Led the payments rewrite.", after: "Led the payments rewrite across four services.", reason: "JD asks for payments scope" }],
  source_document: {
    filename: "maya-chen-resume.docx",
    paragraphs: [{ id: "p-3", text: "Led the payments rewrite.", role: "bullet", section: "Experience" }],
    sections: [{ heading: "Experience", paragraph_ids: ["p-3"] }],
  },
} as unknown as PackageOut;

const pkg = { current: tunePackage };
const one = [{ id: "pkg-1", version: 1, status: "blocked", created_at: "2026-09-11T00:00:00Z" }];
const state = { versions: one as unknown[], queue: [] as unknown[], jobTitle: "Staff Engineer" as string | null };
vi.mock("@/components/review/useArchiveAndHide", () => ({ useArchiveAndHide: () => ({ archiveAndHide: vi.fn(), isPending: false }) }));

vi.mock("@/lib/api/queries", () => ({
  useJob: () => ({ data: { id: "j1", company: "Northwind", title: state.jobTitle, jd_text: "jd", url: null }, error: null }),
  usePackage: () => ({ data: pkg.current, error: null }),
  usePackages: () => ({ data: state.versions, error: null }),
  useBlocks: () => ({ data: [], error: null }),
  useApplications: () => ({ data: { columns: {} }, error: null }),
  usePackageList: () => ({ data: state.queue, error: null }),
  useMarkPackageReady: () => ({ mutateAsync: vi.fn(), isPending: false }),
  usePatchPackage: () => ({ mutateAsync: vi.fn() }),
  usePatchPackageEdits: () => ({ mutateAsync: vi.fn() }),
  useAnswers: () => ({ data: { name: "Maya Chen" } }),
  useMarkApplied: () => ({ markApplied: vi.fn(), isPending: false }),
  useTailor: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useTracks: () => ({ data: [] }),
  useResumeDocument: () => ({ data: null, isPending: false }),
}));

import PackageReviewPage from "./page";

describe("PackageReviewPage", () => {
  it("renders the Changes pane instead of the resume and source-block panes for a tune package", () => {
    pkg.current = tunePackage;
    render(<PackageReviewPage />);

    expect(screen.getByRole("heading", { name: "Changes" })).toBeInTheDocument();
    expect(screen.getByLabelText("After")).toHaveValue("Led the payments rewrite across four services.");
    expect(screen.queryByText(/select a bullet to see the block/i)).not.toBeInTheDocument();
  });

  it("shows nothing about calls, tokens, cost, the track or the version, in the header, actions or Truth check", () => {
    const usage = { ...tunePackage, status: "draft", llm_calls: 3, input_tokens: 1200, output_tokens: 340, cost_usd: 0.58, track_id: "3f2b8c1e-9a4d-4e6f-8b7a-1c2d3e4f5a6b" } as unknown as PackageOut;
    pkg.current = usage;
    const { container } = render(<PackageReviewPage />);
    const header = container.querySelector("[data-testid=resume-header]")!.cloneNode(true) as HTMLElement;
    const truth = document.getElementById("guardrails-heading")!.closest("section")!.cloneNode(true) as HTMLElement;
    truth.querySelectorAll("details").forEach((d) => d.remove());
    for (const region of [header, truth]) {
      const text = region.textContent ?? "";
      expect(text).not.toMatch(/LLM|tokens|track |\$|[0-9a-f]{8}-[0-9a-f]{4}/i);
      expect(text).not.toMatch(/package/i);
    }
    expect(document.body.textContent).not.toContain("Change log");
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Staff Engineer");
  });

  it("reads My resumes then Company - Role in the breadcrumb, with no version crumb", () => {
    pkg.current = tunePackage;
    render(<PackageReviewPage />);
    const crumbs = within(screen.getByRole("navigation", { name: "Breadcrumb" })).getAllByRole("listitem");
    expect(crumbs.map((c) => c.textContent?.replace("›", "").trim())).toEqual(["My resumes", "Northwind – Staff Engineer"]);
  });

  it("falls back to 'Tailored resume' when the job has no title", () => {
    pkg.current = tunePackage;
    state.jobTitle = null;
    render(<PackageReviewPage />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Tailored resume");
    state.jobTitle = "Staff Engineer";
  });

  it("shows the version switcher only when there is more than one version", () => {
    pkg.current = tunePackage;
    const first = render(<PackageReviewPage />);
    expect(screen.queryByRole("combobox", { name: "Resume version" })).not.toBeInTheDocument();
    first.unmount();
    state.versions = [...one, { id: "pkg-2", version: 2, status: "draft", created_at: "2026-09-12T00:00:00Z" }];
    render(<PackageReviewPage />);
    expect(screen.getByRole("combobox", { name: "Resume version" })).toBeInTheDocument();
    state.versions = one;
  });

  it("puts a plain status in the header", () => {
    pkg.current = { ...tunePackage, status: "draft" } as unknown as PackageOut;
    render(<PackageReviewPage />);
    expect(screen.getByTestId("resume-header")).toHaveTextContent("Draft");
    expect(screen.getByRole("button", { name: "Mark ready to send" })).toBeInTheDocument();
  });

  it("ends with the next resume to review when there is one", () => {
    pkg.current = tunePackage;
    state.queue = [{ id: "pkg-1", job_id: "j1" }, { id: "pkg-9", job_id: "j9" }];
    render(<PackageReviewPage />);
    expect(screen.getByRole("link", { name: "Next resume to review →" })).toHaveAttribute("href", "/jobs/j9/packages/pkg-9");
    state.queue = [];
  });

  it("ends by counting the changes reviewed in light-touch mode, and says all caught up otherwise", () => {
    pkg.current = tunePackage;
    const first = render(<PackageReviewPage />);
    expect(screen.getByText("You have reviewed all 1 change.")).toBeInTheDocument();
    first.unmount();
    pkg.current = { ...tunePackage, edits: [tunePackage.edits[0], tunePackage.edits[0]] } as unknown as PackageOut;
    const second = render(<PackageReviewPage />);
    expect(screen.getByText("You have reviewed all 2 changes.")).toBeInTheDocument();
    second.unmount();
    pkg.current = { ...tunePackage, edits: [] } as unknown as PackageOut;
    const third = render(<PackageReviewPage />);
    expect(screen.getByText("No lines were changed for this job.")).toBeInTheDocument();
    expect(document.body.textContent).not.toContain("all 0");
    third.unmount();
    pkg.current = { ...tunePackage, mode: "blocks", edits: [], source_document: null, guardrail_report: { passed: true, rules_run: [], violations: [] } } as unknown as PackageOut;
    render(<PackageReviewPage />);
    expect(screen.getByText("You're all caught up.")).toBeInTheDocument();
  });

  it("scrolls the matching change card into view when a tune violation is selected", async () => {
    pkg.current = tunePackage;
    const scrollIntoView = vi.fn();
    Element.prototype.scrollIntoView = scrollIntoView;
    render(<PackageReviewPage />);

    await userEvent.setup({ delay: null }).click(screen.getByRole("button", { name: /rewrote a protected line/i }));
    expect(scrollIntoView).toHaveBeenCalled();
    expect(document.getElementById("change-0")).toHaveAttribute("data-violation", "true");
  });

  it("scrolls to the cover note and to the Changes heading for the non-card violation paths", async () => {
    pkg.current = {
      ...tunePackage,
      guardrail_report: {
        passed: false,
        rules_run: ["tune-scope", "no-new-numbers"],
        violations: [
          { rule: "no-new-numbers", severity: "error", message: "cover note invents a number", path: "cover_note", block_id: null },
          { rule: "tune-scope", severity: "error", message: "too many bullet edits", path: "edits", block_id: null },
        ],
      },
    } as unknown as PackageOut;
    render(<PackageReviewPage />);
    const coverNote = document.getElementById("cover-note");
    const changes = document.getElementById("changes");
    const scrollCoverNote = vi.fn();
    const scrollChanges = vi.fn();
    coverNote!.scrollIntoView = scrollCoverNote;
    changes!.scrollIntoView = scrollChanges;
    const user = userEvent.setup({ delay: null });

    await user.click(screen.getByRole("button", { name: /cover note invents a number/i }));
    expect(scrollCoverNote).toHaveBeenCalled();
    expect(scrollChanges).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: /too many bullet edits/i }));
    expect(scrollChanges).toHaveBeenCalled();
  });

  it("marks a violating change's After textarea aria-invalid", () => {
    pkg.current = tunePackage;
    render(<PackageReviewPage />);
    expect(screen.getByLabelText("After")).toHaveAttribute("aria-invalid", "true");
  });

  it("still renders the resume and source-block panes for a blocks package", () => {
    pkg.current = { ...tunePackage, mode: "blocks", edits: [], source_document: null, guardrail_report: { passed: true, rules_run: [], violations: [] } } as unknown as PackageOut;
    render(<PackageReviewPage />);

    expect(screen.queryByRole("heading", { name: "Changes" })).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Maya Chen" })).toBeInTheDocument();
    expect(screen.getByText(/select a bullet to see the block/i)).toBeInTheDocument();
  });
});
