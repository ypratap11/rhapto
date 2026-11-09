import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { vi } from "vitest";

export function renderWithClient(ui: ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

export type FetchCall = { url: string; method: string; body: unknown };

/** Replaces global fetch with a router: the first matching [method, path-substring] wins. */
export function mockFetch(routes: Array<[string, string, number, unknown]>) {
  const calls: FetchCall[] = [];
  const spy = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    const method = init?.method ?? "GET";
    calls.push({ url, method, body: typeof init?.body === "string" ? JSON.parse(init.body) : undefined });
    const hit = routes.find(([m, p]) => m === method && url.includes(p));
    if (!hit) return new Response("{}", { status: 404 });
    return new Response(JSON.stringify(hit[3]), { status: hit[2], headers: { "content-type": "application/json" } });
  });
  return { calls, spy };
}
