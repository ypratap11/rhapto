import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { JobCard } from "./JobCard";
import type { JobOut } from "@/lib/api/queries";

vi.mock("./TailorButton", () => ({ TailorButton: () => <button>Tailor</button> }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));

const rescueMutateAsync = vi.fn();
const markApplied = vi.fn();
vi.mock("@/lib/api/queries", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/queries")>()),
  useRescueJob: () => ({ mutateAsync: rescueMutateAsync, isPending: false }),
  useMarkApplied: () => ({ markApplied, isPending: false }),
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const job: JobOut = {
  id: "j1",
  source: "greenhouse",
  company: "ExampleCo",
  title: "Data Platform Program Manager",
  location: null,
  url: "https://example.com/job",
  jd_text: "lorem",
  extracted: null,
  discovered_at: "2026-09-09T10:00:00Z",
  latest_package: { id: "p1", version: 2, status: "blocked", created_at: "2026-09-09T11:00:00Z" },
  application_status: "queued",
  best_fit: 82,
  best_track_id: "t1",
  bucket: "fit",
  rescued: false,
  repost_of: null,
  posted_at: null,
  scores: [],
};

const tracks = { t1: { name: "Data PM", min_fit: 60 } };

function renderCard(overrides: Partial<JobOut> = {}) {
  return render(<JobCard job={{ ...job, ...overrides }} onDelete={vi.fn()} tracks={tracks} />);
}

describe("JobCard", () => {
  it("shows company, title, package and application badges, and the Review action for a package", () => {
    renderCard();
    expect(screen.getByText("ExampleCo")).toBeInTheDocument();
    expect(screen.getByText("Data Platform Program Manager")).toBeInTheDocument();
    expect(screen.getByText(/v2 · blocked/i)).toBeInTheDocument();
    expect(screen.getByText("Queued")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /review/i })).toHaveAttribute("href", "/jobs/j1/packages/p1");
    expect(screen.getByRole("link", { name: /posting/i })).toHaveAttribute("href", "https://example.com/job");
  });

  it("no longer renders the underlined Review package link", () => {
    renderCard();
    expect(screen.queryByText("Review package")).not.toBeInTheDocument();
  });

  it("shows the fit badge, source chip, and a re-post marker", () => {
    renderCard({ repost_of: "j0" });
    expect(screen.getByText("82")).toBeInTheDocument();
    expect(screen.getByText("Data PM")).toBeInTheDocument();
    expect(screen.getByText("Greenhouse")).toBeInTheDocument();
    expect(screen.getByText("Re-post")).toBeInTheDocument();
  });

  it("offers Rescue only for low-bucket jobs and moves them to the fit list", async () => {
    renderCard({ bucket: "low" });
    const user = userEvent.setup({ delay: null });
    await user.click(screen.getByRole("button", { name: /rescue/i }));
    expect(rescueMutateAsync).toHaveBeenCalledWith("j1");
    const { toast } = await import("sonner");
    expect(toast.success).toHaveBeenCalledWith("Moved to the fit list");
  });

  it("hides Rescue for fit-bucket jobs", () => {
    renderCard({ bucket: "fit" });
    expect(screen.queryByRole("button", { name: /rescue/i })).not.toBeInTheDocument();
  });

  it("renders the Tailor stub for a job with no package", () => {
    renderCard({ latest_package: null, application_status: null });
    expect(screen.getByRole("button", { name: "Tailor" })).toBeInTheDocument();
  });
});
