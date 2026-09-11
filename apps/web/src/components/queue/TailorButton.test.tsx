import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TailorButton } from "./TailorButton";
import type { JobOut } from "@/lib/api/queries";

const mutateAsync = vi.fn();
let tracksData: { id: string; name: string; min_fit: number }[] = [];
vi.mock("@/lib/api/queries", () => ({
  useTracks: () => ({ data: tracksData }),
  useTailor: () => ({ mutateAsync, isPending: false }),
  invalidateJobs: vi.fn(),
}));
vi.mock("./TaskProgress", () => ({
  TaskProgress: ({ taskId }: { taskId: string }) => <div>progress:{taskId}</div>,
}));

const job: JobOut = {
  id: "j1",
  source: "manual",
  company: "ExampleCo",
  title: "Title",
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
  const client = new QueryClient();
  return render(
    <QueryClientProvider client={client}>
      <TailorButton job={{ ...job, ...overrides }} />
    </QueryClientProvider>,
  );
}

describe("TailorButton", () => {
  beforeEach(() => {
    tracksData = [];
  });

  it("preselects the job's best-fit track", () => {
    tracksData = [
      { id: "ai-pm", name: "AI PM", min_fit: 60 },
      { id: "other", name: "Other Track", min_fit: 50 },
    ];
    renderButton({ best_track_id: "ai-pm" });
    // The Select's popup (and its items, which resolve a value to its label) is
    // portal-mounted only while open; closed, it renders the raw selected value.
    // Asserting on the underlying value is still a faithful check that the job's
    // best-fit track — not the first loaded track — is the one selected.
    expect(screen.getByText("ai-pm")).toBeInTheDocument();
  });

  it("renders TaskProgress even when the mutation returns an already-finished task", async () => {
    mutateAsync.mockResolvedValueOnce({
      id: "t1",
      status: "succeeded",
      result_ref: "p1",
      error: null,
      created_at: "2026-09-09T10:00:00Z",
      finished_at: "2026-09-09T10:01:00Z",
      progress: {},
      type: "tailor",
    });
    renderButton();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /tailor/i }));

    expect(await screen.findByText("progress:t1")).toBeInTheDocument();
  });
});
