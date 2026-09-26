import { describe, expect, it, vi } from "vitest";
import { DELETE, GET, POST } from "./route";

// A syntactically valid compact JWS (three base64url segments) -- not a real Cloudflare token,
// just something that matches the shape the route requires.
const EDGE_JWS = "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ1c2VyQGV4YW1wbGUuY29tIn0.c2lnbmF0dXJl";

describe("api proxy route", () => {
  it("drops the client's Authorization header", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ status: "ok" }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    const request = new Request("http://localhost:3000/api/v1/health", {
      headers: {
        "Cf-Access-Jwt-Assertion": EDGE_JWS,
        Authorization: "Bearer client-supplied-should-be-dropped",
      },
    });
    const response = await GET(request, { params: Promise.resolve({ path: ["health"] }) });
    expect(response.status).toBe(200);
    // fetchSpy.mock.calls[0] is `unknown[] | undefined` under noUncheckedIndexedAccess
    // (tsconfig.json:8) -- chain the optional access rather than indexing calls[0] directly
    // (re-review breakage item 4).
    const forwardedHeaders = fetchSpy.mock.calls[0]?.[1]?.headers as Headers;
    expect(forwardedHeaders.get("Cf-Access-Jwt-Assertion")).toBe(EDGE_JWS);
    expect(forwardedHeaders.has("authorization")).toBe(false);
    fetchSpy.mockRestore();
  });

  it("refuses a request carrying two Cf-Access-Jwt-Assertion values, and never forwards either", async () => {
    // Headers.get joins repeated headers with ", ", so a client that appends its own assertion
    // alongside the edge's genuine one would otherwise smuggle "client-forged, edge-issued"
    // straight to the API (fix-round finding S1).
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    const headers = new Headers();
    headers.append("Cf-Access-Jwt-Assertion", "client-forged");
    headers.append("Cf-Access-Jwt-Assertion", EDGE_JWS);
    const request = new Request("http://localhost:3000/api/v1/health", { headers });
    const response = await GET(request, { params: Promise.resolve({ path: ["health"] }) });
    expect(response.status).toBe(403);
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });

  it("refuses a single Cf-Access-Jwt-Assertion that is not a well-formed compact JWS", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    const request = new Request("http://localhost:3000/api/v1/health", {
      headers: { "Cf-Access-Jwt-Assertion": "not-a-jws" },
    });
    const response = await GET(request, { params: Promise.resolve({ path: ["health"] }) });
    expect(response.status).toBe(403);
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });

  it("drops the client's Cookie header", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(null, { status: 200 }));
    const request = new Request("http://localhost:3000/api/v1/health", { headers: { Cookie: "session=abc" } });
    await GET(request, { params: Promise.resolve({ path: ["health"] }) });
    const forwardedHeaders = fetchSpy.mock.calls[0]?.[1]?.headers as Headers;
    expect(forwardedHeaders.has("cookie")).toBe(false);
    fetchSpy.mockRestore();
  });

  it("forwards accept and content-type", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(null, { status: 200 }));
    const request = new Request("http://localhost:3000/api/v1/health", {
      headers: { accept: "application/json", "content-type": "application/json" },
    });
    await GET(request, { params: Promise.resolve({ path: ["health"] }) });
    const forwardedHeaders = fetchSpy.mock.calls[0]?.[1]?.headers as Headers;
    expect(forwardedHeaders.get("accept")).toBe("application/json");
    expect(forwardedHeaders.get("content-type")).toBe("application/json");
    fetchSpy.mockRestore();
  });

  it("keeps a percent-decoded '..' segment inside /api/v1 instead of letting URL parsing escape it", async () => {
    // App Router params arrive percent-decoded, so a request for .../..%2F..%2Fopenapi.json is
    // handed to this route as the single path element "../../openapi.json". Re-encoding each
    // segment before building the upstream URL keeps that decoded "/" literal rather than letting
    // `new URL` treat it as a directory separator (fix-round finding S2).
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(null, { status: 404 }));
    const request = new Request("http://localhost:3000/api/v1/openapi.json");
    await GET(request, { params: Promise.resolve({ path: ["../../openapi.json"] }) });
    const calledUrl = fetchSpy.mock.calls[0]?.[0] as URL;
    expect(calledUrl.pathname).toBe("/api/v1/..%2F..%2Fopenapi.json");
    fetchSpy.mockRestore();
  });

  it("forwards the query string", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(null, { status: 200 }));
    const request = new Request("http://localhost:3000/api/v1/jobs?search=foo&bar=baz");
    await GET(request, { params: Promise.resolve({ path: ["jobs"] }) });
    const calledUrl = fetchSpy.mock.calls[0]?.[0] as URL;
    expect(calledUrl.search).toBe("?search=foo&bar=baz");
    fetchSpy.mockRestore();
  });

  it("forwards a POST body", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(null, { status: 201 }));
    const request = new Request("http://localhost:3000/api/v1/jobs", {
      method: "POST",
      body: JSON.stringify({ a: 1 }),
      headers: { "content-type": "application/json" },
    });
    const response = await POST(request, { params: Promise.resolve({ path: ["jobs"] }) });
    expect(response.status).toBe(201);
    // `duplex` is a real, Node-supported RequestInit field that the installed DOM lib does not
    // type yet (see FetchInitWithDuplex in route.ts) -- widen locally rather than in the route.
    const init = fetchSpy.mock.calls[0]?.[1] as (RequestInit & { duplex?: string }) | undefined;
    expect(init?.method).toBe("POST");
    expect(init?.body).not.toBeUndefined();
    expect(init?.duplex).toBe("half");
    fetchSpy.mockRestore();
  });

  it("sends no body for a DELETE with none", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(null, { status: 204 }));
    const request = new Request("http://localhost:3000/api/v1/jobs/abc", { method: "DELETE" });
    const response = await DELETE(request, { params: Promise.resolve({ path: ["jobs", "abc"] }) });
    expect(response.status).toBe(204);
    const init = fetchSpy.mock.calls[0]?.[1];
    // A DELETE with no body arrives as `request.body === null` (not `undefined`); the route passes
    // that straight through rather than coercing it, which is fine for fetch either way.
    expect(init?.body).toBeNull();
    fetchSpy.mockRestore();
  });

  it("passes a non-2xx upstream status straight through", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ title: "Not Found" }), {
        status: 404,
        headers: { "content-type": "application/problem+json" },
      }),
    );
    const request = new Request("http://localhost:3000/api/v1/jobs/nope");
    const response = await GET(request, { params: Promise.resolve({ path: ["jobs", "nope"] }) });
    expect(response.status).toBe(404);
    fetchSpy.mockRestore();
  });

  it("marks an SSE upstream response no-store, no-transform, with buffering disabled", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response("data: {}\n\n", {
        status: 200,
        headers: { "content-type": "text/event-stream" },
      }),
    );
    const request = new Request("http://localhost:3000/api/v1/tasks/abc/events");
    const response = await GET(request, { params: Promise.resolve({ path: ["tasks", "abc", "events"] }) });
    // `no-transform` is the load-bearing directive: it is the only thing that stops Next's own
    // compression middleware from buffering the stream into a single gzipped chunk (finding C1).
    expect(response.headers.get("Cache-Control")).toBe("no-store, no-transform");
    expect(response.headers.get("X-Accel-Buffering")).toBe("no");
    fetchSpy.mockRestore();
  });
});
