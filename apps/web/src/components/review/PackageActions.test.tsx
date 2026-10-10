import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { toast } from "sonner";
import { describe, expect, it, vi } from "vitest";
import { PackageActions } from "./PackageActions";
import type { ApplicationOut, JobOut, PackageOut } from "@/lib/api/queries";

const downloadAuthenticated = vi.fn();
vi.mock("@/lib/download", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/download")>()),
  downloadAuthenticated: (path: string, filename: string) => downloadAuthenticated(path, filename) as Promise<void>,
}));

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const markApplied = vi.fn();
vi.mock("@/lib/api/queries", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/queries")>()),
  useAnswers: () => ({ data: { name: "Maya Chen" } }),
  useMarkApplied: () => ({ markApplied, isPending: false }),
}));

const job = { id: "j1", url: "https://example.com/jobs/1" } as JobOut;
const pkg = { id: "p1", version: 1, has_pdf: true, has_docx: true } as PackageOut;

describe("PackageActions", () => {
  it("downloads a candidate-named PDF", async () => {
    downloadAuthenticated.mockResolvedValueOnce(undefined);
    render(<PackageActions job={job} pkg={pkg} application={null} onRegenerate={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: /download pdf/i }));
    expect(downloadAuthenticated).toHaveBeenCalledWith("/api/v1/packages/p1/files/resume.pdf", "Maya_Chen_Resume.pdf");
  });

  it("downloads a candidate-named DOCX", async () => {
    downloadAuthenticated.mockResolvedValueOnce(undefined);
    render(<PackageActions job={job} pkg={pkg} application={null} onRegenerate={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: /download docx/i }));
    expect(downloadAuthenticated).toHaveBeenCalledWith("/api/v1/packages/p1/files/resume.docx", "Maya_Chen_Resume.docx");
  });

  it("downloads a candidate-named zip", async () => {
    downloadAuthenticated.mockResolvedValueOnce(undefined);
    render(<PackageActions job={job} pkg={pkg} application={null} onRegenerate={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: /download zip/i }));
    expect(downloadAuthenticated).toHaveBeenCalledWith("/api/v1/packages/p1/download", "Maya_Chen_Package.zip");
  });

  it("disables PDF/DOCX downloads when the files do not exist", () => {
    render(<PackageActions job={job} pkg={{ ...pkg, has_pdf: false, has_docx: false }} application={null} onRegenerate={vi.fn()} />);
    expect(screen.getByRole("button", { name: /download pdf/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /download docx/i })).toBeDisabled();
  });

  it("disables PDF/DOCX downloads for a blocked package even when legacy files exist, and says why", () => {
    // A package blocked before documents were withheld still has files on disk (has_docx/has_pdf
    // true), and the server answers 409. The buttons must not offer what will be refused.
    render(<PackageActions job={job} pkg={{ ...pkg, status: "blocked" }} application={null} onRegenerate={vi.fn()} />);
    const pdf = screen.getByRole("button", { name: /download pdf/i });
    const docx = screen.getByRole("button", { name: /download docx/i });
    expect(pdf).toBeDisabled();
    expect(docx).toBeDisabled();
    const reason = screen.getByText(/guardrails blocked this package/i);
    expect(pdf).toHaveAttribute("aria-describedby", reason.id);
    expect(docx).toHaveAttribute("aria-describedby", reason.id);
    // The zip stays available: it carries the report and GUARDRAILS-BLOCKED.md, never a document.
    expect(screen.getByRole("button", { name: /download zip/i })).toBeEnabled();
  });

  it("keeps PDF/DOCX enabled and shows no blocked note for a draft package", () => {
    render(<PackageActions job={job} pkg={{ ...pkg, status: "draft" }} application={null} onRegenerate={vi.fn()} />);
    expect(screen.getByRole("button", { name: /download pdf/i })).toBeEnabled();
    expect(screen.getByRole("button", { name: /download docx/i })).toBeEnabled();
    expect(screen.queryByText(/guardrails blocked this package/i)).not.toBeInTheDocument();
  });

  it("calls onRegenerate when Regenerate is clicked", async () => {
    const onRegenerate = vi.fn();
    render(<PackageActions job={job} pkg={pkg} application={null} onRegenerate={onRegenerate} />);
    await userEvent.click(screen.getByRole("button", { name: /regenerate/i }));
    expect(onRegenerate).toHaveBeenCalledTimes(1);
  });

  it("marks the package applied via useMarkApplied", async () => {
    markApplied.mockResolvedValueOnce(undefined);
    const application = { id: "a1", status: "queued" } as ApplicationOut;
    render(<PackageActions job={job} pkg={pkg} application={application} onRegenerate={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: /mark applied/i }));
    expect(markApplied).toHaveBeenCalledWith(job, "p1", application);
  });

  it("offers the dashboard after marking applied", async () => {
    markApplied.mockResolvedValueOnce(undefined);
    render(<PackageActions job={job} pkg={pkg} application={null} onRegenerate={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: /mark applied/i }));
    const [message, options] = vi.mocked(toast.success).mock.calls.at(-1)!;
    expect(message).toBe("Marked as applied");
    expect(options?.action).toMatchObject({ label: "Open dashboard" });
    (options!.action as unknown as { onClick: () => void }).onClick();
    expect(push).toHaveBeenCalledWith("/dashboard");
  });

  it("shows the status badge instead of Mark applied once already applied", () => {
    const application = { id: "a1", status: "applied" } as ApplicationOut;
    render(<PackageActions job={job} pkg={pkg} application={application} onRegenerate={vi.fn()} />);
    expect(screen.queryByRole("button", { name: /mark applied/i })).not.toBeInTheDocument();
    expect(screen.getByText("Applied")).toBeInTheDocument();
  });

  it("links to the posting when a job url is present", () => {
    render(<PackageActions job={job} pkg={pkg} application={null} onRegenerate={vi.fn()} />);
    expect(screen.getByRole("link", { name: /open posting/i })).toHaveAttribute("href", job.url);
  });
});
