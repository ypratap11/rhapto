import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DEFAULT_SEARCH_STATE } from "@/lib/search-state";
import { useLiveSearch } from "./queries";

const post = vi.fn();
const get = vi.fn();
vi.mock("./client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("./client")>()),
  apiClient: () => ({ POST: post, GET: get }),
}));

const ok = <T,>(data: T) => Promise.resolve({ data, response: new Response(null, { status: 200 }) });
const job = (id: string, fit: number | null) => ({ id, best_fit: fit, company: "ExampleCo", title: "Program Manager" });

function wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

beforeEach(() => vi.useFakeTimers({ shouldAdvanceTime: true }));
afterEach(() => {
  vi.useRealTimers();
  vi.clearAllMocks();
});

describe("useLiveSearch", () => {
  it("refetches the unscored jobs every 3s and stops once all are scored", async () => {
    post.mockReturnValue(ok({ jobs: [job("j1", 80), job("j2", null)], per_source: { themuse: { found: 2, new: 1 } } }));
    get.mockReturnValueOnce(ok([job("j1", 80), job("j2", null)])).mockReturnValue(ok([job("j1", 80), job("j2", 71)]));

    const { result } = renderHook(() => useLiveSearch(), { wrapper });
    act(() => result.current.run({ ...DEFAULT_SEARCH_STATE, query: "pm" }));

    await waitFor(() => expect(result.current.status).toBe("scoring"));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });
    expect(get).toHaveBeenCalledTimes(1);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });
    await waitFor(() => expect(result.current.status).toBe("done"));
    expect(result.current.jobs.map((j) => j.best_fit)).toEqual([80, 71]);

    const calls = get.mock.calls.length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(9000);
    });
    expect(get).toHaveBeenCalledTimes(calls);
  });

  it("gives up after 60s, keeps the unscored jobs on screen, and stops polling", async () => {
    post.mockReturnValue(ok({ jobs: [job("j1", null)], per_source: {} }));
    get.mockReturnValue(ok([job("j1", null)]));

    const { result } = renderHook(() => useLiveSearch(), { wrapper });
    act(() => result.current.run({ ...DEFAULT_SEARCH_STATE, query: "pm" }));
    await waitFor(() => expect(result.current.status).toBe("scoring"));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(61_000);
    });
    await waitFor(() => expect(result.current.status).toBe("done"));
    expect(result.current.jobs).toHaveLength(1);

    // Same rigour as the "all scored" test above: the ceiling has to actually clear the interval,
    // not just flip the status once.
    const calls = get.mock.calls.length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(9000);
    });
    expect(get).toHaveBeenCalledTimes(calls);
  });

  it("sets status to error when the initial search fails, and never starts a poll interval", async () => {
    post.mockRejectedValue(new Error("network down"));

    const { result } = renderHook(() => useLiveSearch(), { wrapper });
    act(() => result.current.run({ ...DEFAULT_SEARCH_STATE, query: "pm" }));

    await waitFor(() => expect(result.current.status).toBe("error"));
    expect(result.current.error).toBeInstanceOf(Error);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(30_000);
    });
    expect(get).not.toHaveBeenCalled();
  });

  it("sets status to error and stops polling when a poll GET fails", async () => {
    post.mockReturnValue(ok({ jobs: [job("j1", null)], per_source: {} }));
    get.mockRejectedValue(new Error("timeout"));

    const { result } = renderHook(() => useLiveSearch(), { wrapper });
    act(() => result.current.run({ ...DEFAULT_SEARCH_STATE, query: "pm" }));
    await waitFor(() => expect(result.current.status).toBe("scoring"));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });
    await waitFor(() => expect(result.current.status).toBe("error"));
    expect(result.current.error).toBeInstanceOf(Error);

    const calls = get.mock.calls.length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(9000);
    });
    expect(get).toHaveBeenCalledTimes(calls);
  });

  // Not from the plan's test list, but the plan flags a leaked interval as a real hazard here
  // (it surfaces as cross-test pollution, not a clean failure), so unmount cleanup gets its own case.
  it("clears its poll interval on unmount instead of leaking it", async () => {
    post.mockReturnValue(ok({ jobs: [job("j1", null)], per_source: {} }));
    get.mockReturnValue(ok([job("j1", null)]));

    const { result, unmount } = renderHook(() => useLiveSearch(), { wrapper });
    act(() => result.current.run({ ...DEFAULT_SEARCH_STATE, query: "pm" }));
    await waitFor(() => expect(result.current.status).toBe("scoring"));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });
    const callsBeforeUnmount = get.mock.calls.length;
    expect(callsBeforeUnmount).toBeGreaterThan(0);

    unmount();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30_000);
    });
    expect(get).toHaveBeenCalledTimes(callsBeforeUnmount);
  });

  // Regression for the leak the first review round found: the earlier `useEffect(() => stop, [stop])`
  // clears `timer.current` exactly once, at unmount — but if the component unmounts before the
  // initial POST resolves, `timer.current` is still null at that point, so the cleanup does nothing.
  // The POST then resolves later, `setInterval` runs against an unmounted hook, and nothing ever
  // calls `clearInterval` again: it polls forever. This must fail against the unfixed hook.
  it("does not start a poll interval if the component unmounts while the initial POST is still pending", async () => {
    let resolvePost!: (value: unknown) => void;
    post.mockReturnValue(
      new Promise((resolve) => {
        resolvePost = resolve;
      }),
    );

    const { result, unmount } = renderHook(() => useLiveSearch(), { wrapper });
    act(() => result.current.run({ ...DEFAULT_SEARCH_STATE, query: "pm" }));
    expect(result.current.status).toBe("searching");

    unmount();

    // The POST resolves only after teardown — with unscored jobs, so an unguarded hook would start
    // setInterval right here.
    await act(async () => {
      resolvePost({ data: { jobs: [job("j1", null)], per_source: {} }, response: new Response(null, { status: 200 }) });
      await vi.advanceTimersByTimeAsync(30_000);
    });

    expect(get).not.toHaveBeenCalled();
  });

  // Same leak, reached by calling run() twice instead of unmounting: the first call's POST is still
  // in flight when the second call's run() fires. The first call's continuation resolving later must
  // not resurrect a second, orphaned interval, and must not clobber the second (current) run's state.
  it("does not leak an interval when run() is called again while the previous POST is still pending", async () => {
    let resolveFirst!: (value: unknown) => void;
    post
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolveFirst = resolve;
          }),
      )
      .mockReturnValueOnce(ok({ jobs: [job("j2", 90)], per_source: {} }));

    const { result } = renderHook(() => useLiveSearch(), { wrapper });
    act(() => result.current.run({ ...DEFAULT_SEARCH_STATE, query: "first" }));
    act(() => result.current.run({ ...DEFAULT_SEARCH_STATE, query: "second" }));
    expect(post).toHaveBeenCalledTimes(2);

    // The second (current) run's POST already resolved with a fully-scored job, so it's done — no
    // interval from this run either.
    await waitFor(() => expect(result.current.status).toBe("done"));
    expect(result.current.jobs.map((j) => j.id)).toEqual(["j2"]);

    // Now let the stale first run's POST resolve, with unscored jobs that would start its own
    // interval if the hook didn't know it had been superseded.
    await act(async () => {
      resolveFirst({ data: { jobs: [job("j1", null)], per_source: {} }, response: new Response(null, { status: 200 }) });
      await vi.advanceTimersByTimeAsync(30_000);
    });

    expect(get).not.toHaveBeenCalled();
    // And the stale run must not have overwritten the current run's already-settled result.
    expect(result.current.jobs.map((j) => j.id)).toEqual(["j2"]);
  });
});
