import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { proxy } from "./proxy";

const JWS = "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ1c2VyQGV4YW1wbGUuY29tIn0.c2lnbmF0dXJl";
let fetchSpy: ReturnType<typeof vi.spyOn>;
const req = (assertion?: string) =>
  new NextRequest("http://localhost/admin", { headers: assertion === undefined ? {} : { "cf-access-jwt-assertion": assertion } });

beforeEach(() => {
  fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("{}", { status: 200 }));
});
afterEach(() => fetchSpy.mockRestore());

describe("admin proxy", () => {
  it("answers 404 without an assertion and does not call the API", async () => {
    expect((await proxy(req())).status).toBe(404);
    expect(fetchSpy).not.toHaveBeenCalled();
  });
  it("answers 404 for a malformed assertion", async () => {
    expect((await proxy(req(`x, ${JWS}`))).status).toBe(404);
    expect(fetchSpy).not.toHaveBeenCalled();
  });
  it("answers 404 when the API says 404, 503, or is unreachable", async () => {
    fetchSpy.mockResolvedValue(new Response("{}", { status: 404 }));
    expect((await proxy(req(JWS))).status).toBe(404);
    fetchSpy.mockResolvedValue(new Response("{}", { status: 503 }));
    expect((await proxy(req(JWS))).status).toBe(404);
    fetchSpy.mockRejectedValue(new TypeError("network"));
    expect((await proxy(req(JWS))).status).toBe(404);
  });
  it("lets an admin through", async () => {
    const res = await proxy(req(JWS));
    expect(res.status).toBe(200);
    expect(res.headers.get("x-middleware-next")).toBe("1");
  });
});
