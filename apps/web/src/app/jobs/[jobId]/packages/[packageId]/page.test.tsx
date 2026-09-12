import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { PackageOut } from "@/lib/api/queries";

vi.mock("next/navigation", () => ({
  useParams: () => ({ jobId: "j1", packageId: "pkg-1" }),
  useRouter: () => ({ push: vi.fn() }),
}));

const tunePackage = {
  id: "pkg-1",
  job_id: "j1",
  version: 1,
  status: "blocked",
  mode: "tune",
  track_id: "platform",
  llm_calls: 1,
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

vi.mock("@/lib/api/queries", () => ({
  useJob: () => ({ data: { id: "j1", company: "Northwind", title: "Staff Engineer", jd_text: "jd", url: null }, error: null }),
  usePackage: () => ({ data: pkg.current, error: null }),
  usePackages: () => ({ data: [{ id: "pkg-1", version: 1, status: "blocked", created_at: "2026-09-11T00:00:00Z" }], error: null }),
  useBlocks: () => ({ data: [], error: null }),
  useApplications: () => ({ data: { columns: {} }, error: null }),
  usePackageList: () => ({ data: [], error: null }),
  usePatchPackage: () => ({ mutateAsync: vi.fn() }),
  usePatchPackageEdits: () => ({ mutateAsync: vi.fn() }),
  useAnswers: () => ({ data: { name: "Maya Chen" } }),
  useMarkApplied: () => ({ markApplied: vi.fn(), isPending: false }),
  useTailor: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useTracks: () => ({ data: [] }),
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
