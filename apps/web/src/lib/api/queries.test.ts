import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "./client";
import { keys, PACKAGE_LIST_PARAMS, useJobsEmptyReason, useLlmSettings, useMarkApplied, useSimilarPostings, type JobFilters } from "./queries";
import { DEFAULT_SEARCH_STATE } from "@/lib/search-state";

const postMock = vi.fn();
const patchMock = vi.fn();
const getMock = vi.fn();

vi.mock("./client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("./client")>()),
  apiClient: () => ({ POST: postMock, PATCH: patchMock, GET: getMock, DELETE: vi.fn(), PUT: vi.fn() }),
}));

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient();
  return createElement(QueryClientProvider, { client }, children);
}

/**
 * One client per hook under test, with retries off: a query wrapper that built a new QueryClient on
 * every render would reset the query it is meant to observe, and the default three retries would
 * make the rejecting cases slow.
 */
function queryWrapper() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client }, children);
  };
}

describe("useMarkApplied", () => {
  it("recovers from a 409 (existing application) by patching that application to applied", async () => {
    postMock.mockRejectedValueOnce(new ApiError(409, { title: "Conflict", status: 409, existing_application_id: "a9" }, "HTTP 409"));
    patchMock.mockResolvedValueOnce({ data: { id: "a9", status: "applied" }, response: { ok: true } });

    const { result } = renderHook(() => useMarkApplied(), { wrapper });
    await act(async () => {
      await result.current.markApplied({ id: "j1" }, "p1", null);
    });

    expect(postMock).toHaveBeenCalledWith("/api/v1/applications", { body: { job_id: "j1", package_id: "p1" } });
    expect(patchMock).toHaveBeenCalledWith("/api/v1/applications/{application_id}", {
      params: { path: { application_id: "a9" } },
      body: { status: "applied" },
    });
  });
});

describe("keys.jobs", () => {
  const filters = (over: Partial<JobFilters>): JobFilters => ({ search: "", track: null, tab: "new", region: "us", sort: "fit", ...over });

  it("shares one cache entry between New and Tailored so switching tabs doesn't refetch", () => {
    expect(keys.jobs(filters({ tab: "new" }))).toEqual(keys.jobs(filters({ tab: "tailored" })));
  });

  it("keys Low fit separately", () => {
    expect(keys.jobs(filters({ tab: "new" }))).not.toEqual(keys.jobs(filters({ tab: "low" })));
  });

  it("keys each region separately, because the server filters on it", () => {
    expect(keys.jobs(filters({ region: "us" }))).not.toEqual(keys.jobs(filters({ region: "any" })));
    expect(keys.jobs(filters({ region: "us" }))).not.toEqual(keys.jobs(filters({ region: "preferred" })));
  });
});

describe("PACKAGE_LIST_PARAMS", () => {
  it("maps each PackageListFilter to its query params", () => {
    expect(PACKAGE_LIST_PARAMS.review).toEqual({ applied: false, status: "draft", archived: false });
    expect(PACKAGE_LIST_PARAMS.ready).toEqual({ applied: false, status: "ready", archived: false });
    expect(PACKAGE_LIST_PARAMS.blocked).toEqual({ status: "blocked", archived: false });
    expect(PACKAGE_LIST_PARAMS.applied).toEqual({ applied: true });
  });
});

describe("useLlmSettings", () => {
  beforeEach(() => {
    getMock.mockReset();
  });

  /** What openapi-fetch hands `unwrap` for an RFC-7807 response, so the real ApiError is built here. */
  function problemResponse(status: number, detail: string, code?: string, extra: Record<string, unknown> = {}) {
    return { error: { type: "about:blank", title: "Conflict", status, detail, ...(code ? { code } : {}), ...extra }, response: { ok: false, status } };
  }

  it("folds a 409 llm_key_unreadable into the unreadable state, carrying the detail", async () => {
    getMock.mockResolvedValue(problemResponse(409, "your stored API key could not be read; re-enter it", "llm_key_unreadable"));

    const { result } = renderHook(() => useLlmSettings(), { wrapper: queryWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data).toEqual({
      kind: "unreadable",
      detail: "your stored API key could not be read; re-enter it",
      providers: [],
    });
    expect(getMock).toHaveBeenCalledWith("/api/v1/settings/llm");
  });

  it("carries the 409's provider list into the unreadable state", async () => {
    // This 409 replaces the 200 that normally holds `providers`, and the Settings picker has to be
    // rendered from it rather than from a copy of the registry in the web app.
    const providers = [{ id: "openai", label: "OpenAI", models: ["gpt-5", "gpt-5-mini"], default: "gpt-5" }];
    getMock.mockResolvedValue(problemResponse(409, "re-enter it", "llm_key_unreadable", { providers }));

    const { result } = renderHook(() => useLlmSettings(), { wrapper: queryWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data).toEqual({ kind: "unreadable", detail: "re-enter it", providers });
  });

  it("keeps a 409 carrying any other code a query error", async () => {
    // Widening the catch to "any 409" would hide a real conflict behind the re-enter-your-key form.
    getMock.mockResolvedValue(problemResponse(409, "something else entirely", "some_other_conflict"));

    const { result } = renderHook(() => useLlmSettings(), { wrapper: queryWrapper() });
    await waitFor(() => expect(result.current.isError).toBe(true));

    expect(result.current.data).toBeUndefined();
    expect(result.current.error).toBeInstanceOf(ApiError);
    expect((result.current.error as ApiError).status).toBe(409);
  });

  it("keeps a 500 a query error", async () => {
    getMock.mockResolvedValue({ error: { title: "Internal Server Error", status: 500, detail: "boom" }, response: { ok: false, status: 500 } });

    const { result } = renderHook(() => useLlmSettings(), { wrapper: queryWrapper() });
    await waitFor(() => expect(result.current.isError).toBe(true));

    expect((result.current.error as ApiError).status).toBe(500);
  });

  it("returns the settings as the ok state on success", async () => {
    const settings = {
      provider: "openai",
      model: "gpt-5",
      key_set: true,
      key_hint: "…1234",
      source: "settings" as const,
      providers: [{ id: "openai", label: "OpenAI", models: ["gpt-5"], default: "gpt-5" }],
    };
    getMock.mockResolvedValue({ data: settings, response: { ok: true, status: 200 } });

    const { result } = renderHook(() => useLlmSettings(), { wrapper: queryWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data).toEqual({ kind: "ok", settings });
  });
});

describe("useJobsEmptyReason", () => {
  beforeEach(() => {
    getMock.mockReset();
  });

  it("does not fire while the grid has rows", async () => {
    // The contract the whole companion-endpoint design rests on. The diagnosis is N+1 aggregate
    // counts over the user's corpus; paying for them on a page that already has rows is work whose
    // answer is thrown away, and the architecture rejected putting the reason on the list response
    // for exactly this reason. `enabled: false` is what makes that real rather than intended.
    renderHook(() => useJobsEmptyReason(DEFAULT_SEARCH_STATE, { enabled: false }), { wrapper: queryWrapper() });
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(getMock).not.toHaveBeenCalled();
  });

  it("asks the companion endpoint once the grid is empty", async () => {
    getMock.mockResolvedValue({ data: { total: 0, cause: "no_jobs", user_field_names: [] }, response: { ok: true } });
    const { result } = renderHook(() => useJobsEmptyReason(DEFAULT_SEARCH_STATE, { enabled: true }), {
      wrapper: queryWrapper(),
    });
    await waitFor(() => expect(result.current.data).toBeDefined());
    expect(getMock).toHaveBeenCalledWith("/api/v1/jobs/empty-reason", expect.anything());
  });

  it("sends the same filters the listing sent, so the diagnosis describes that exact query", async () => {
    getMock.mockResolvedValue({ data: { total: 0, cause: "no_jobs", user_field_names: [] }, response: { ok: true } });
    const state = { ...DEFAULT_SEARCH_STATE, posted_within: "24h" as const, sources: ["adzuna"], field: "engineering" };
    const { result } = renderHook(() => useJobsEmptyReason(state, { enabled: true, searchId: "s1" }), {
      wrapper: queryWrapper(),
    });
    await waitFor(() => expect(result.current.data).toBeDefined());
    expect(getMock).toHaveBeenCalledWith("/api/v1/jobs/empty-reason", {
      params: {
        query: { sort: "relevance", posted_within: "24h", sources: "adzuna", field: "engineering", search_id: "s1" },
      },
    });
  });
});

describe("useSimilarPostings", () => {
  beforeEach(() => {
    getMock.mockReset();
    getMock.mockResolvedValue({ data: [], response: { ok: true } });
  });

  it("asks GET /jobs for exactly those ids, newest first, with no age window", async () => {
    const { result } = renderHook(() => useSimilarPostings(["a", "b"], true), { wrapper: queryWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(getMock).toHaveBeenCalledTimes(1);
    expect(getMock).toHaveBeenCalledWith("/api/v1/jobs", {
      params: { query: { ids: "a,b", sort: "newest", posted_within: "any" } },
    });
  });

  it("sends nothing until it is enabled", async () => {
    renderHook(() => useSimilarPostings(["a", "b"], false), { wrapper: queryWrapper() });
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(getMock).not.toHaveBeenCalled();
  });

  it("sends nothing for an empty id list, even when enabled", async () => {
    renderHook(() => useSimilarPostings([], true), { wrapper: queryWrapper() });
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(getMock).not.toHaveBeenCalled();
  });

  it("sends at most 200 ids, the API's cap", async () => {
    const ids = Array.from({ length: 250 }, (_, i) => `id${i}`);
    const { result } = renderHook(() => useSimilarPostings(ids, true), { wrapper: queryWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    const sent = (getMock.mock.calls[0][1] as { params: { query: { ids: string } } }).params.query.ids.split(",");
    expect(sent).toHaveLength(200);
    expect(sent[199]).toBe("id199");
  });
});
