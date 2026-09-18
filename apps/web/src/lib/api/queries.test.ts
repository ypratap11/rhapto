import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "./client";
import { keys, PACKAGE_LIST_PARAMS, useLlmSettings, useMarkApplied, type JobFilters } from "./queries";

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
