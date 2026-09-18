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

  it("gives up after 60s and keeps the unscored jobs on screen", async () => {
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
  });
});
