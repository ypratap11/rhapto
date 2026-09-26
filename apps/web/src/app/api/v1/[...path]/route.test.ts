import { describe, expect, it, vi } from "vitest";
import { GET } from "./route";

describe("api proxy route", () => {
  it("strips a client-supplied Cf-Access-Jwt-Assertion and forwards the edge's own", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ status: "ok" }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    const request = new Request("http://localhost:3000/api/v1/health", {
      headers: {
        "Cf-Access-Jwt-Assertion": "edge-issued-token",
        Authorization: "Bearer client-supplied-should-be-dropped",
      },
    });
    const response = await GET(request, { params: Promise.resolve({ path: ["health"] }) });
    expect(response.status).toBe(200);
    // fetchSpy.mock.calls[0] is `unknown[] | undefined` under noUncheckedIndexedAccess
    // (tsconfig.json:8) -- chain the optional access rather than indexing calls[0] directly
    // (re-review breakage item 4).
    const forwardedHeaders = fetchSpy.mock.calls[0]?.[1]?.headers as Headers;
    expect(forwardedHeaders.get("Cf-Access-Jwt-Assertion")).toBe("edge-issued-token");
    expect(forwardedHeaders.has("authorization")).toBe(false);
    fetchSpy.mockRestore();
  });

  it("marks an SSE upstream response no-store with buffering disabled", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response("data: {}\n\n", {
        status: 200,
        headers: { "content-type": "text/event-stream" },
      }),
    );
    const request = new Request("http://localhost:3000/api/v1/tasks/abc/events");
    const response = await GET(request, { params: Promise.resolve({ path: ["tasks", "abc", "events"] }) });
    expect(response.headers.get("Cache-Control")).toBe("no-store");
    expect(response.headers.get("X-Accel-Buffering")).toBe("no");
    fetchSpy.mockRestore();
  });
});
