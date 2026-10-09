import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { TaskEvent } from "@/lib/api/sse";
import { TailorStep } from "./TailorStep";

const driver: { emit: (e: TaskEvent) => void; end: () => void; aborted: boolean } = { emit: () => undefined, end: () => undefined, aborted: false };
vi.mock("@/lib/api/sse", () => ({
  readTaskEvents: vi.fn((_id: string, cb: (e: TaskEvent) => void, signal?: AbortSignal) =>
    new Promise<void>((resolve) => {
      driver.aborted = false;
      driver.emit = cb;
      driver.end = resolve;
      signal?.addEventListener("abort", () => { driver.aborted = true; resolve(); });
    }),
  ),
}));

const props = () => ({ taskId: "t1", onDone: vi.fn(), onRetry: vi.fn(), onPickAnother: vi.fn() });

beforeEach(() => vi.useFakeTimers({ shouldAdvanceTime: true }));
afterEach(() => vi.useRealTimers());

describe("TailorStep", () => {
  it("narrates the run in plain words, never the engine's step names", () => {
    render(<TailorStep {...props()} />);
    act(() => driver.emit({ event: "progress", data: { step: "tune" } }));
    expect(screen.getByText("Rewriting your resume for it")).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/\btune\b|\bvalidate\b|\brender\b/);
  });

  it("says others are ahead of you when no step has been reported for a while", () => {
    render(<TailorStep {...props()} />);
    expect(screen.queryByText(/others are ahead of you/i)).toBeNull();
    act(() => { vi.advanceTimersByTime(20_001); });
    expect(screen.getByText("Still working, others are ahead of you")).toBeInTheDocument();
    act(() => driver.emit({ event: "progress", data: { step: "extract" } }));
    expect(screen.queryByText(/others are ahead of you/i)).toBeNull();
  });

  it("hands the package id on exactly once when the run finishes", async () => {
    const p = props();
    render(<TailorStep {...p} />);
    act(() => driver.emit({ event: "done", data: { package_id: "pk1", status: "draft" } }));
    act(() => driver.end());
    await waitFor(() => expect(p.onDone).toHaveBeenCalledTimes(1));
    expect(p.onDone).toHaveBeenCalledWith("pk1");
  });

  it("re-attaching to a task that already finished replays its state and still completes", async () => {
    const p = props();
    render(<TailorStep {...p} />);
    act(() => driver.emit({ event: "state", data: { status: "succeeded", result_ref: "pk9", progress: { step: "render", request: { mode: "tune" } } } }));
    act(() => driver.end());
    await waitFor(() => expect(p.onDone).toHaveBeenCalledWith("pk9"));
  });

  it("a failed run shows the reason and two ways forward", async () => {
    const p = props();
    render(<TailorStep {...p} />);
    act(() => driver.emit({ event: "error", data: { message: "The model returned an unreadable answer." } }));
    act(() => driver.end());
    expect(await screen.findByRole("alert")).toHaveTextContent("The model returned an unreadable answer.");
    const user = userEvent.setup({ delay: null, advanceTimers: vi.advanceTimersByTime });
    await user.click(screen.getByRole("button", { name: /try again/i }));
    await user.click(screen.getByRole("button", { name: /pick another job/i }));
    expect(p.onRetry).toHaveBeenCalledTimes(1);
    expect(p.onPickAnother).toHaveBeenCalledTimes(1);
    expect(p.onDone).not.toHaveBeenCalled();
  });

  it("a dropped connection tells the tester to reload, which re-attaches through the URL", async () => {
    render(<TailorStep {...props()} />);
    act(() => driver.emit({ event: "progress", data: { step: "tune" } }));
    act(() => driver.end());
    expect(await screen.findByText(/reload this page/i)).toBeInTheDocument();
  });

  it("stops listening when it unmounts", () => {
    const { unmount } = render(<TailorStep {...props()} />);
    unmount();
    expect(driver.aborted).toBe(true);
  });
});
