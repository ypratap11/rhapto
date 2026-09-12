import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { JobActionButton } from "./JobActionButton";
import type { JobOut } from "@/lib/api/queries";

vi.mock("./TailorButton", () => ({ TailorButton: () => <button>Tailor</button> }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));

const markApplied = vi.fn();
vi.mock("@/lib/api/queries", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/queries")>()),
  useMarkApplied: () => ({ markApplied, isPending: false }),
}));

const job: JobOut = {
  id: "j1",
  source: "manual",
  company: "ExampleCo",
  title: "Data PM",
  location: null,
  url: null,
  jd_text: "lorem",
  extracted: null,
  discovered_at: "2026-09-09T10:00:00Z",
  latest_package: null,
  application_status: null,
  rescued: false,
  scores: [],
};

function renderButton(overrides: Partial<JobOut> = {}) {
  return render(<JobActionButton job={{ ...job, ...overrides }} />);
}

describe("JobActionButton", () => {
  it("renders the TailorButton stub for a job with no package", () => {
    renderButton();
    expect(screen.getByRole("button", { name: "Tailor" })).toBeInTheDocument();
  });

  it("renders Review and Mark applied for a job with a package and no application", async () => {
    const pkg = { id: "p1", version: 1, status: "draft" as const, mode: "blocks" as const, created_at: "2026-09-09T10:00:00Z" };
    renderButton({ latest_package: pkg });
    const link = screen.getByRole("link", { name: /review/i });
    expect(link).toHaveAttribute("href", "/jobs/j1/packages/p1");
    const user = userEvent.setup({ delay: null });
    await user.click(screen.getByRole("button", { name: /mark applied/i }));
    expect(markApplied).toHaveBeenCalledWith(expect.objectContaining({ id: "j1" }), "p1", null);
  });

  it("renders the Applied badge for an applied job", () => {
    const pkg = { id: "p1", version: 1, status: "draft" as const, mode: "blocks" as const, created_at: "2026-09-09T10:00:00Z" };
    renderButton({ latest_package: pkg, application_status: "applied" });
    expect(screen.getByText("Applied")).toBeInTheDocument();
  });
});
