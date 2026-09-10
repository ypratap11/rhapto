import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { TaskProgress } from "./TaskProgress";
import { readTaskEvents } from "@/lib/api/sse";
import { toast } from "sonner";

vi.mock("@/lib/api/sse", () => ({ readTaskEvents: vi.fn() }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const mockReadTaskEvents = vi.mocked(readTaskEvents);
const toastSuccess = vi.mocked(toast.success);
const toastError = vi.mocked(toast.error);

afterEach(() => {
  mockReadTaskEvents.mockReset();
  toastSuccess.mockClear();
  toastError.mockClear();
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
    const { unmount } = render(<TaskProgress taskId="t1" jobId="j1" onFinished={onFinished} />);
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
      onEvent({ event: "state", data: { status: "running", progress: { step: "render" } } });
      return new Promise<void>(() => undefined);
    });
    render(<TaskProgress taskId="t2" jobId="j1" onFinished={vi.fn()} />);

    for (const step of ["extract", "select", "compose", "validate", "repair"]) {
      expect(screen.getByText(step).className).toContain("border-green-300");
    }
    expect(screen.getByText("render").className).toContain("border-accent");
  });
});
