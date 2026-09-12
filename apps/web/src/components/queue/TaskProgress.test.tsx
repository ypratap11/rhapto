import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { TaskProgress } from "./TaskProgress";
import { readTaskEvents } from "@/lib/api/sse";
import { toast } from "sonner";

vi.mock("@/lib/api/sse", () => ({ readTaskEvents: vi.fn() }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const resolvePackageStatus = vi.fn();
vi.mock("@/lib/task-progress", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/task-progress")>()),
  resolvePackageStatus: (packageId: string) => resolvePackageStatus(packageId) as Promise<string | null>,
}));

const mockReadTaskEvents = vi.mocked(readTaskEvents);
const toastSuccess = vi.mocked(toast.success);
const toastError = vi.mocked(toast.error);

function renderTaskProgress(props: { taskId: string; jobId: string; onFinished: (state: unknown) => void; kind?: "tailor" | "poll" }) {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <TaskProgress {...props} />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  mockReadTaskEvents.mockReset();
  toastSuccess.mockClear();
  toastError.mockClear();
  resolvePackageStatus.mockReset();
});

describe("TaskProgress", () => {
  it("does not report an abort from unmount as a failure", async () => {
    mockReadTaskEvents.mockImplementation(
      (_taskId, _onEvent, signal) =>
        new Promise<void>((_resolve, reject) => {
          signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
        }),
    );
    const onFinished = vi.fn();
    const { unmount } = renderTaskProgress({ taskId: "t1", jobId: "j1", onFinished });
    unmount();
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();

    expect(onFinished).not.toHaveBeenCalled();
    expect(toastSuccess).not.toHaveBeenCalled();
    expect(toastError).not.toHaveBeenCalled();
  });

  it("marks the steps before the active one done and the active one active", () => {
    mockReadTaskEvents.mockImplementation((_taskId, onEvent) => {
      onEvent({ event: "state", data: { status: "running", progress: { step: "render", request: { mode: "blocks" } } } });
      return new Promise<void>(() => undefined);
    });
    renderTaskProgress({ taskId: "t2", jobId: "j1", onFinished: vi.fn() });

    for (const step of ["extract", "select", "compose", "validate", "repair"]) {
      expect(screen.getByText(step).className).toContain("border-green-300");
    }
    // A blocks run never tunes, so claiming a finished `tune` step would be a lie.
    expect(screen.queryByText("tune")).not.toBeInTheDocument();
    expect(screen.getByText("render").className).toContain("border-accent");
  });

  it("shows a tune run its own pills: tune, and no select or compose", () => {
    mockReadTaskEvents.mockImplementation((_taskId, onEvent) => {
      onEvent({ event: "state", data: { status: "running", progress: { step: "validate", request: { mode: "tune" } } } });
      return new Promise<void>(() => undefined);
    });
    renderTaskProgress({ taskId: "t2b", jobId: "j1", onFinished: vi.fn() });

    expect(screen.getByText("tune").className).toContain("border-green-300");
    expect(screen.queryByText("select")).not.toBeInTheDocument();
    expect(screen.queryByText("compose")).not.toBeInTheDocument();
    expect(screen.getByText("validate").className).toContain("border-accent");
  });

  it("resolves the real package status on a state-replay and never announces a blocked package as ready", async () => {
    resolvePackageStatus.mockResolvedValueOnce("blocked");
    mockReadTaskEvents.mockImplementation(async (_taskId, onEvent) => {
      onEvent({ event: "state", data: { status: "succeeded", result_ref: "pkg1", progress: {} } });
    });
    const onFinished = vi.fn();
    renderTaskProgress({ taskId: "t3", jobId: "j1", onFinished });

    await vi.waitFor(() => expect(onFinished).toHaveBeenCalled());
    expect(resolvePackageStatus).toHaveBeenCalledWith("pkg1");
    expect(toastSuccess).toHaveBeenCalledTimes(1);
    expect(toastSuccess.mock.calls[0]?.[0]).not.toBe("Package ready");
    expect(toastSuccess).toHaveBeenCalledWith("Package blocked by guardrails", expect.anything());
    expect(await screen.findByText(/open package \(blocked\)/i)).toBeInTheDocument();
  });

  it("uses neutral copy when the fallback status lookup also fails", async () => {
    resolvePackageStatus.mockResolvedValueOnce(null);
    mockReadTaskEvents.mockImplementation(async (_taskId, onEvent) => {
      onEvent({ event: "state", data: { status: "succeeded", result_ref: "pkg1", progress: {} } });
    });
    renderTaskProgress({ taskId: "t4", jobId: "j1", onFinished: vi.fn() });

    await vi.waitFor(() => expect(toastSuccess).toHaveBeenCalled());
    expect(toastSuccess).toHaveBeenCalledWith("Package created — open the review", expect.anything());
  });

  it("toasts an interruption when the stream ends without a terminal event", async () => {
    mockReadTaskEvents.mockImplementation(async (_taskId, onEvent) => {
      onEvent({ event: "progress", data: { step: "compose" } });
    });
    const onFinished = vi.fn();
    renderTaskProgress({ taskId: "t5", jobId: "j1", onFinished });

    await vi.waitFor(() => expect(onFinished).toHaveBeenCalled());
    expect(toastError).toHaveBeenCalledWith("Tailoring was interrupted; refresh to check the job");
    expect(toastSuccess).not.toHaveBeenCalled();
  });

  it("in poll mode, renders the poll steps and toasts the new-job count without a package lookup", async () => {
    mockReadTaskEvents.mockImplementation(async (_taskId, onEvent) => {
      onEvent({ event: "done", data: { event: "done", new_jobs: 3 } });
    });
    const onFinished = vi.fn();
    renderTaskProgress({ taskId: "t6", jobId: "", onFinished, kind: "poll" });

    expect(screen.getByText("fetch")).toBeInTheDocument();
    expect(screen.getByText("score")).toBeInTheDocument();
    await vi.waitFor(() => expect(onFinished).toHaveBeenCalled());
    expect(resolvePackageStatus).not.toHaveBeenCalled();
    expect(toastSuccess).toHaveBeenCalledWith("Poll finished: 3 new jobs");
    expect(toastError).not.toHaveBeenCalled();
  });

  it("in poll mode, toasts when there are no new jobs", async () => {
    mockReadTaskEvents.mockImplementation(async (_taskId, onEvent) => {
      onEvent({ event: "done", data: { event: "done", new_jobs: 0 } });
    });
    const onFinished = vi.fn();
    renderTaskProgress({ taskId: "t7", jobId: "", onFinished, kind: "poll" });

    await vi.waitFor(() => expect(onFinished).toHaveBeenCalled());
    expect(toastSuccess).toHaveBeenCalledWith("Poll finished: no new jobs");
  });

  it("in poll mode, reads the new-job count from a state-replay's result_ref instead of claiming zero", async () => {
    mockReadTaskEvents.mockImplementation(async (_taskId, onEvent) => {
      onEvent({ event: "state", data: { status: "succeeded", result_ref: "new:3", progress: {} } });
    });
    const onFinished = vi.fn();
    renderTaskProgress({ taskId: "t8", jobId: "", onFinished, kind: "poll" });

    await vi.waitFor(() => expect(onFinished).toHaveBeenCalled());
    expect(resolvePackageStatus).not.toHaveBeenCalled();
    expect(toastSuccess).toHaveBeenCalledWith("Poll finished: 3 new jobs");
  });

  it("in poll mode, toasts a neutral message when a state-replay carries no parsable count", async () => {
    mockReadTaskEvents.mockImplementation(async (_taskId, onEvent) => {
      onEvent({ event: "state", data: { status: "succeeded", result_ref: null, progress: {} } });
    });
    const onFinished = vi.fn();
    renderTaskProgress({ taskId: "t9", jobId: "", onFinished, kind: "poll" });

    await vi.waitFor(() => expect(onFinished).toHaveBeenCalled());
    expect(toastSuccess).toHaveBeenCalledWith("Poll finished");
  });
});
