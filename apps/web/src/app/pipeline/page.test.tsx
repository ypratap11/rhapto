import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/client";
import type { ApplicationOut, JobOut } from "@/lib/api/queries";

function application(over: Partial<ApplicationOut> & { id: string; job: ApplicationOut["job"]; status: string }): ApplicationOut {
  return {
    applied_at: null,
    closed_reason: null,
    created_at: "2026-09-01T00:00:00Z",
    follow_up_at: null,
    notes: "",
    package_id: null,
    status_history: [],
    updated_at: "2026-09-01T00:00:00Z",
    ...over,
  } as ApplicationOut;
}

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

type ApplicationsResult = { data: { columns: Record<string, ApplicationOut[]> } | undefined; error: unknown; isPaused?: boolean };

let applicationsResult: ApplicationsResult = { data: { columns: {} }, error: null };
let jobResult: { data: JobOut | undefined; error: unknown; isLoading: boolean } = { data: job(), error: null, isLoading: false };
const patchMutateAsync = vi.fn().mockResolvedValue({});
const deleteMutateAsync = vi.fn().mockResolvedValue({});

vi.mock("@/lib/api/queries", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/queries")>()),
  useApplications: () => applicationsResult,
  usePatchApplication: () => ({ mutateAsync: patchMutateAsync, isPending: false }),
  useDeleteApplication: () => ({ mutateAsync: deleteMutateAsync, isPending: false }),
  useJob: () => jobResult,
}));

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

vi.mock("@dnd-kit/core", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@dnd-kit/core")>();
  return {
    ...actual,
    useDraggable: () => ({ attributes: {}, listeners: {}, setNodeRef: () => undefined, transform: null, isDragging: false }),
    useDroppable: () => ({ setNodeRef: () => undefined, isOver: false }),
    DndContext: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  };
});

import PipelinePage from "./page";
import PipelineBoardPage from "./board/page";

const columns = (over: Partial<Record<string, ApplicationOut[]>>) => ({
  discovered: [],
  queued: [],
  applied: [],
  screen: [],
  interview: [],
  offer: [],
  closed: [],
  ...over,
});

describe("PipelinePage", () => {
  it("shows shape-matched skeletons while loading, not an empty or error state", () => {
    applicationsResult = { data: undefined, error: null };
    const { container } = render(<PipelinePage />);
    expect(container.querySelector('[data-slot="table-skeleton"]')).toBeInTheDocument();
    expect(container.querySelector('[data-slot="skeleton"]')).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.queryByText(/pick an application/i)).not.toBeInTheDocument();
  });

  it("shows only an error banner when the API is unreachable and nothing is cached", () => {
    applicationsResult = { data: undefined, error: null, isPaused: true };
    render(<PipelinePage />);
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.queryByText(/pick an application/i)).not.toBeInTheDocument();
  });

  it("keeps showing cached applications alongside a banner when a background refetch fails", () => {
    applicationsResult = {
      data: { columns: columns({ applied: [application({ id: "a1", job: { id: "j1", company: "ExampleCo", title: "TPM" }, status: "applied" })] }) },
      error: new ApiError(500, null, "Server error"),
    };
    render(<PipelinePage />);
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getAllByText("ExampleCo").length).toBeGreaterThan(0);
  });

  it("shows the Pick-an-application empty state when nothing is selected, and its own two columns", () => {
    applicationsResult = { data: { columns: columns({}) }, error: null };
    render(<PipelinePage />);
    expect(screen.getByLabelText("Search applications")).toBeInTheDocument();
    expect(screen.getByText(/pick an application/i)).toBeInTheDocument();
  });

  it("selects a card and renders its detail with a Pipeline › company · role breadcrumb", async () => {
    // A distinct company/title from either application, so the JdPane's own text (sourced from
    // this static useJob mock, not the selected application) can never collide with the assertions
    // below on the list card / breadcrumb text.
    jobResult = { data: job({ id: "j1", company: "JobBoardCo", title: "Listing" }), error: null, isLoading: false };
    applicationsResult = {
      data: {
        columns: columns({
          applied: [
            application({ id: "a0", job: { id: "j0", company: "OtherCo", title: "Eng" }, status: "applied" }),
            application({ id: "a1", job: { id: "j1", company: "ExampleCo", title: "TPM" }, status: "applied" }),
          ],
        }),
      },
      error: null,
    };
    const user = userEvent.setup({ delay: null });
    render(<PipelinePage />);
    // The first row (OtherCo) is the default selection until a card is picked.
    expect(document.title).toBe("Pipeline › OtherCo · Eng");
    expect(screen.getByText("OtherCo · Eng")).toBeInTheDocument();

    await user.click(screen.getByText("ExampleCo"));
    expect(document.title).toBe("Pipeline › ExampleCo · TPM");
    expect(screen.getByText("ExampleCo · TPM")).toBeInTheDocument();
  });

  it("never defaults the selection to a discovered/queued application that has no card in any tab", () => {
    // discovered/queued flatten in ahead of applied (Object.values order), so a naive rows[0]
    // would open the detail pane on an application ApplicationList can't render as current.
    jobResult = { data: job({ id: "j2", company: "VisibleCo", title: "Eng" }), error: null, isLoading: false };
    applicationsResult = {
      data: {
        columns: columns({
          discovered: [application({ id: "d1", job: { id: "jd", company: "GhostCo", title: "Ghost" }, status: "discovered" })],
          queued: [application({ id: "q1", job: { id: "jq", company: "QueuedCo", title: "Queued" }, status: "queued" })],
          applied: [application({ id: "a1", job: { id: "j2", company: "VisibleCo", title: "Eng" }, status: "applied" })],
        }),
      },
      error: null,
    };
    render(<PipelinePage />);

    expect(document.title).toBe("Pipeline › VisibleCo · Eng");
    expect(screen.queryByText("GhostCo")).not.toBeInTheDocument();
    expect(screen.queryByText("QueuedCo")).not.toBeInTheDocument();

    const card = screen.getAllByText("VisibleCo").map((el) => el.closest("button")).find((btn) => btn !== null);
    expect(card).not.toBeUndefined();
    expect(card).toHaveAttribute("aria-current", "true");
  });

  it("keeps the default selection fixed after a refetch reorders the visible rows (acting on it must not move it)", () => {
    jobResult = { data: job({ id: "j0", company: "OtherCo", title: "Eng" }), error: null, isLoading: false };
    applicationsResult = {
      data: {
        columns: columns({
          applied: [
            application({ id: "a0", job: { id: "j0", company: "OtherCo", title: "Eng" }, status: "applied" }),
            application({ id: "a1", job: { id: "j1", company: "ExampleCo", title: "TPM" }, status: "applied" }),
          ],
        }),
      },
      error: null,
    };
    const { rerender } = render(<PipelinePage />);
    expect(document.title).toBe("Pipeline › OtherCo · Eng");

    // Simulate the refetch that follows acting on the default-selected application (a0): its
    // status moves it to a different bucket, which reorders the flattened rows so a1 (ExampleCo)
    // would now be rows[0] if the default were re-derived on every render.
    applicationsResult = {
      data: {
        columns: columns({
          applied: [application({ id: "a1", job: { id: "j1", company: "ExampleCo", title: "TPM" }, status: "applied" })],
          screen: [application({ id: "a0", job: { id: "j0", company: "OtherCo", title: "Eng" }, status: "screen" })],
        }),
      },
      error: null,
    };
    rerender(<PipelinePage />);

    // The visible selection must not have jumped to ExampleCo just because it is now rows[0].
    expect(document.title).toBe("Pipeline › OtherCo · Eng");
  });
});

describe("PipelineBoardPage", () => {
  it("still renders the Kanban board, unchanged, behind its own breadcrumb", () => {
    applicationsResult = { data: { columns: columns({ applied: [application({ id: "a1", job: { id: "j1", company: "ExampleCo", title: "TPM" }, status: "applied" })] }) }, error: null };
    render(<PipelineBoardPage />);
    expect(document.title).toBe("Pipeline › Board");
    expect(screen.getByRole("region", { name: "Applied column" })).toBeInTheDocument();
    expect(screen.getByText("ExampleCo")).toBeInTheDocument();
  });
});
