import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setSettings } from "@/lib/api/client";
import { useCoachMatches } from "./matches";

const routes: { trackJobs: unknown[]; cause: string; ready: boolean } = { trackJobs: [], cause: "filter", ready: false };
const requests: string[] = [];

function respond(url: URL): unknown {
  requests.push(url.pathname + url.search);
  if (url.pathname.endsWith("/coach/readiness")) return { ready: routes.ready };
  if (url.pathname.endsWith("/jobs/empty-reason")) return { total: 5, cause: routes.cause };
  if (url.pathname.endsWith("/jobs")) return routes.trackJobs;
  throw new Error(`unrouted ${url.pathname}`);
}

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  requests.length = 0;
  Object.assign(routes, { trackJobs: [], cause: "filter", ready: false });
  setSettings({ token: "tok", apiUrl: "http://localhost:8000" });
  vi.stubGlobal("fetch", vi.fn(async (input: Request) => new Response(JSON.stringify(respond(new URL(input.url))), { status: 200, headers: { "content-type": "application/json" } })));
});
afterEach(() => vi.unstubAllGlobals());

const mk = (id: string) => ({ id, title: id, company: "ExampleCo", best_fit: 70, scores: [] });

describe("useCoachMatches", () => {
  it("asks for the confirmed track's recommended jobs sorted by fit, and for that track's readiness", async () => {
    routes.trackJobs = [mk("a")];
    routes.ready = true;
    const { result } = renderHook(() => useCoachMatches("tpm", { pollMs: 20 }), { wrapper });
    await waitFor(() => expect(result.current.state).toMatchObject({ kind: "ready", final: true }));
    const urls = requests.map((r) => new URL("http://x" + r));
    const jobsCall = urls.find((u) => u.pathname === "/api/v1/jobs")!;
    expect(Object.fromEntries(jobsCall.searchParams)).toEqual({ sort: "fit", recommended: "true", track: "tpm" });
    const readyCall = urls.find((u) => u.pathname === "/api/v1/coach/readiness")!;
    expect(Object.fromEntries(readyCall.searchParams)).toEqual({ track: "tpm" });
  });

  it("plays a rescore forward: partial rows show at once (not final), then the full list arrives and is final", async () => {
    routes.trackJobs = [mk("a")];
    const { result } = renderHook(() => useCoachMatches("tpm", { pollMs: 20 }), { wrapper });
    await waitFor(() => expect(result.current.state).toMatchObject({ kind: "ready", final: false }));
    expect((result.current.state as { jobs: unknown[] }).jobs).toHaveLength(1);
    routes.trackJobs = [mk("a"), mk("b"), mk("c")]; // later chunks commit
    await waitFor(() => expect((result.current.state as { jobs: unknown[] }).jobs).toHaveLength(3));
    expect(result.current.state).toMatchObject({ kind: "ready", final: false }); // still not ready
    routes.ready = true;
    await waitFor(() => expect(result.current.state).toMatchObject({ kind: "ready", final: true }));
    expect((result.current.state as { jobs: unknown[] }).jobs).toHaveLength(3);
  });

  it("an empty list while scoring is pending keeps waiting; it becomes 'no strong matches' only once ready", async () => {
    const { result } = renderHook(() => useCoachMatches("tpm", { pollMs: 20 }), { wrapper });
    await waitFor(() => expect(requests.some((r) => r.includes("/jobs/empty-reason"))).toBe(true));
    await new Promise((r) => setTimeout(r, 100)); // several polls
    expect(result.current.state.kind).toBe("waiting");
    routes.ready = true;
    await waitFor(() => expect(result.current.state).toEqual({ kind: "none", reason: "no_strong_matches" }));
  });

  it("no_jobs is final even before ready", async () => {
    routes.cause = "no_jobs";
    const { result } = renderHook(() => useCoachMatches("tpm", { pollMs: 20 }), { wrapper });
    await waitFor(() => expect(result.current.state).toEqual({ kind: "none", reason: "no_jobs" }));
  });

  it("a readiness error (unknown track) just keeps waiting, it never reads as 'no matches'", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: Request) => {
      const url = new URL(input.url);
      if (url.pathname.endsWith("/coach/readiness")) return new Response(JSON.stringify({ title: "Not Found", status: 404 }), { status: 404, headers: { "content-type": "application/problem+json" } });
      return new Response(JSON.stringify(respond(url)), { status: 200, headers: { "content-type": "application/json" } });
    }));
    const { result } = renderHook(() => useCoachMatches("tpm", { pollMs: 20 }), { wrapper });
    await new Promise((r) => setTimeout(r, 120));
    expect(result.current.state.kind).toBe("waiting");
  });
});
