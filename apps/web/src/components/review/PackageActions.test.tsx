import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { toast } from "sonner";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/client";
import type { ApplicationOut, JobOut, PackageOut } from "@/lib/api/queries";
import { PackageActions } from "./PackageActions";

const downloadAuthenticated = vi.fn();
vi.mock("@/lib/download", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/download")>()),
  downloadAuthenticated: (path: string, filename: string) => downloadAuthenticated(path, filename) as Promise<void>,
}));

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const markApplied = vi.fn();
const markReady = vi.fn();
vi.mock("@/lib/api/queries", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/queries")>()),
  useAnswers: () => ({ data: { name: "Maya Chen" } }),
  useMarkApplied: () => ({ markApplied, isPending: false }),
  useMarkPackageReady: () => ({ mutateAsync: markReady, isPending: false }),
}));

const archiveAndHide = vi.fn();
vi.mock("./useArchiveAndHide", () => ({ useArchiveAndHide: () => ({ archiveAndHide, isPending: false }) }));

const job = { id: "j1", company: "Northwind", title: "Staff Engineer", url: "https://example.com/jobs/1" } as JobOut;
const base = { id: "p1", version: 1, has_pdf: true, has_docx: true } as PackageOut;
const withStatus = (status: string) => ({ ...base, status }) as PackageOut;

function view(p: PackageOut, opts: { application?: ApplicationOut | null; job?: JobOut; onRegenerate?: () => void } = {}) {
  return render(<PackageActions job={opts.job ?? job} pkg={p} application={opts.application ?? null} onRegenerate={opts.onRegenerate ?? vi.fn()} />);
}

/** Elements dressed as the page's one primary action. */
function filled(container: HTMLElement): HTMLElement[] {
  return Array.from(container.querySelectorAll<HTMLElement>("a, button")).filter((el) => el.classList.contains("bg-primary"));
}

async function openMore(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("button", { name: "More" }));
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("PackageActions, one primary per state", () => {
  it("draft: Mark ready to send is the only filled button, with Download beside it", () => {
    const { container } = view(withStatus("draft"));
    expect(filled(container).map((b) => b.textContent)).toEqual(["Mark ready to send"]);
    expect(screen.getByRole("button", { name: "Download" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: APPLIED })).not.toBeInTheDocument();
  });

  it("ready: Download is the only filled button, with I've applied beside it", () => {
    const { container } = view(withStatus("ready"));
    expect(filled(container).map((b) => b.textContent)).toEqual(["Download"]);
    expect(screen.getByRole("button", { name: APPLIED })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Mark ready to send" })).not.toBeInTheDocument();
  });

  it("blocked: nothing filled, no Download and no Word or PDF anywhere, and it says why", async () => {
    const { container } = view(withStatus("blocked"));
    expect(filled(container)).toHaveLength(0);
    expect(screen.queryByRole("button", { name: "Download" })).not.toBeInTheDocument();
    await openMore(userEvent.setup());
    expect(screen.queryByText(/^Word$/)).not.toBeInTheDocument();
    expect(screen.queryByText(/^PDF$/)).not.toBeInTheDocument();
    for (const name of ["Regenerate", "Download everything", "Archive"]) expect(screen.getByRole("button", { name })).toBeInTheDocument();
    expect(
      screen.getByText("This resume was stopped by the truth check, so the documents are not available. Fix the lines above and regenerate; Download everything still holds the report."),
    ).toBeInTheDocument();
  });

  it("applied: a status badge, nothing filled, Download still there, no I've applied", () => {
    const application = { id: "a1", status: "applied" } as ApplicationOut;
    const { container } = view(withStatus("ready"), { application });
    expect(filled(container)).toHaveLength(0);
    expect(screen.getByText("Applied")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Download" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: APPLIED })).not.toBeInTheDocument();
  });

  it("never says Mark applied or Guardrails or package", async () => {
    for (const s of ["draft", "ready", "blocked"]) {
      const { container, unmount } = view(withStatus(s));
      await openMore(userEvent.setup());
      expect(container.textContent).not.toMatch(/mark applied|guardrail|package/i);
      unmount();
    }
  });

  it("makes the primary full width on a phone and tall enough to tap", () => {
    const { container } = view(withStatus("draft"));
    const [primary] = filled(container);
    expect(primary.className).toContain("max-sm:w-full");
    expect(primary.className).toContain("min-h-11");
  });
});

// The label is typed with a straight apostrophe in the product copy.
const APPLIED = "I've applied";

describe("PackageActions, Mark ready to send", () => {
  it("marks the resume ready", async () => {
    markReady.mockResolvedValueOnce({});
    view(withStatus("draft"));
    await userEvent.click(screen.getByRole("button", { name: "Mark ready to send" }));
    expect(markReady).toHaveBeenCalledWith("p1");
  });

  it("shows the API's own message when it refuses (409)", async () => {
    markReady.mockRejectedValueOnce(new ApiError(409, null, "This resume did not pass the truth check."));
    view(withStatus("draft"));
    await userEvent.click(screen.getByRole("button", { name: "Mark ready to send" }));
    expect(toast.error).toHaveBeenCalledWith("This resume did not pass the truth check.");
  });
});

describe("PackageActions, the More menu", () => {
  it("lists Regenerate, Download everything, the posting and Archive for a draft", async () => {
    view(withStatus("draft"));
    await openMore(userEvent.setup());
    expect(screen.getByRole("button", { name: "Regenerate" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Download everything" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open the job posting" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Archive" })).toBeInTheDocument();
  });

  it("opens an https posting safely and never offers a javascript: one", async () => {
    const { unmount } = view(withStatus("draft"));
    await openMore(userEvent.setup());
    const link = screen.getByRole("link", { name: "Open the job posting" });
    expect(link).toHaveAttribute("href", "https://example.com/jobs/1");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
    unmount();
    view(withStatus("draft"), { job: { ...job, url: "javascript:alert(1)" } });
    await openMore(userEvent.setup());
    expect(screen.queryByRole("link", { name: "Open the job posting" })).not.toBeInTheDocument();
  });

  it("calls onRegenerate", async () => {
    const onRegenerate = vi.fn();
    view(withStatus("draft"), { onRegenerate });
    await openMore(userEvent.setup());
    await userEvent.click(screen.getByRole("button", { name: "Regenerate" }));
    expect(onRegenerate).toHaveBeenCalledTimes(1);
  });

  it("archives, then goes back to My resumes", async () => {
    archiveAndHide.mockResolvedValueOnce(true);
    view(withStatus("draft"));
    await openMore(userEvent.setup());
    await userEvent.click(screen.getByRole("button", { name: "Archive" }));
    expect(archiveAndHide).toHaveBeenCalledWith({ packageId: "p1", jobId: "j1", label: "Northwind 00b7 Staff Engineer" });
    expect(push).toHaveBeenCalledWith("/resumes");
  });

  it("stays on the page when archiving failed", async () => {
    archiveAndHide.mockResolvedValueOnce(false);
    view(withStatus("draft"));
    await openMore(userEvent.setup());
    await userEvent.click(screen.getByRole("button", { name: "Archive" }));
    expect(push).not.toHaveBeenCalled();
  });
});

describe("PackageActions, downloads", () => {
  it("offers Word and PDF under Download and names the files after the candidate", async () => {
    downloadAuthenticated.mockResolvedValue(undefined);
    view(withStatus("ready"));
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Download" }));
    await user.click(screen.getByRole("button", { name: "Word" }));
    expect(downloadAuthenticated).toHaveBeenCalledWith("/api/v1/packages/p1/files/resume.docx", "Maya_Chen_Resume.docx");
    await user.click(screen.getByRole("button", { name: "Download" }));
    await user.click(screen.getByRole("button", { name: "PDF" }));
    expect(downloadAuthenticated).toHaveBeenCalledWith("/api/v1/packages/p1/files/resume.pdf", "Maya_Chen_Resume.pdf");
  });

  it("downloads everything as a zip from More", async () => {
    downloadAuthenticated.mockResolvedValueOnce(undefined);
    view(withStatus("ready"));
    const user = userEvent.setup();
    await openMore(user);
    await user.click(screen.getByRole("button", { name: "Download everything" }));
    expect(downloadAuthenticated).toHaveBeenCalledWith("/api/v1/packages/p1/download", "Maya_Chen_Package.zip");
  });

  it("disables a format whose file does not exist", async () => {
    view({ ...withStatus("ready"), has_pdf: false, has_docx: false } as PackageOut);
    await userEvent.click(screen.getByRole("button", { name: "Download" }));
    expect(screen.getByRole("button", { name: "Word" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "PDF" })).toBeDisabled();
  });
});

describe("PackageActions, I've applied", () => {
  it("marks the job applied and offers the dashboard", async () => {
    markApplied.mockResolvedValueOnce(undefined);
    const application = { id: "a1", status: "queued" } as ApplicationOut;
    view(withStatus("ready"), { application });
    await userEvent.click(screen.getByRole("button", { name: APPLIED }));
    expect(markApplied).toHaveBeenCalledWith(job, "p1", application);
    const [message, options] = vi.mocked(toast.success).mock.calls.at(-1)!;
    expect(message).toBe("Marked as applied");
    (options!.action as unknown as { onClick: () => void }).onClick();
    expect(push).toHaveBeenCalledWith("/dashboard");
  });
});
