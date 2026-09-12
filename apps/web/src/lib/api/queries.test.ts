import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { ApiError } from "./client";
import { useMarkApplied } from "./queries";

const postMock = vi.fn();
const patchMock = vi.fn();

vi.mock("./client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("./client")>()),
  apiClient: () => ({ POST: postMock, PATCH: patchMock, GET: vi.fn(), DELETE: vi.fn(), PUT: vi.fn() }),
}));

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient();
  return createElement(QueryClientProvider, { client }, children);
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
