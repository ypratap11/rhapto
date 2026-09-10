import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { TailorButton } from "./TailorButton";
import type { JobOut } from "@/lib/api/queries";

const mutateAsync = vi.fn();
vi.mock("@/lib/api/queries", () => ({
  useTracks: () => ({ data: [] }),
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
};

function renderButton() {
  const client = new QueryClient();
  return render(
    <QueryClientProvider client={client}>
      <TailorButton job={job} />
    </QueryClientProvider>,
  );
}

describe("TailorButton", () => {
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
