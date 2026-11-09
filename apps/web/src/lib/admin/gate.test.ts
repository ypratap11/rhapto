import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { isAdminAssertion } from "./gate";

const JWS = "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ1c2VyQGV4YW1wbGUuY29tIn0.c2lnbmF0dXJl";
let fetchSpy: ReturnType<typeof vi.spyOn>;
beforeEach(() => {
  fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("{}", { status: 200 }));
});
afterEach(() => fetchSpy.mockRestore());

describe("isAdminAssertion", () => {
  it("is false without calling the API for a missing or malformed assertion", async () => {
    expect(await isAdminAssertion(null)).toBe(false);
    expect(await isAdminAssertion("")).toBe(false);
    expect(await isAdminAssertion(`x, ${JWS}`)).toBe(false);
    expect(fetchSpy).not.toHaveBeenCalled();
  });
  it("is true only for exactly 200, forwarding the assertion", async () => {
    expect(await isAdminAssertion(JWS)).toBe(true);
    const init = fetchSpy.mock.calls[0][1] as RequestInit;
    expect(init.headers).toEqual({ "Cf-Access-Jwt-Assertion": JWS });
    expect(String(fetchSpy.mock.calls[0][0])).toMatch(/\/api\/v1\/admin\/session$/);
  });
  it.each([201, 204, 302, 401, 404, 500, 503])("is false when the API answers %i", async (status) => {
    fetchSpy.mockResolvedValue(new Response(status === 204 ? null : "{}", { status }));
    expect(await isAdminAssertion(JWS)).toBe(false);
  });
  it("is false when the API is unreachable", async () => {
    fetchSpy.mockRejectedValue(new TypeError("network"));
    expect(await isAdminAssertion(JWS)).toBe(false);
  });
  it("is false when the API hangs past the timeout", async () => {
    fetchSpy.mockImplementation(((_url: unknown, init?: RequestInit) => new Promise((_, reject) => init?.signal?.addEventListener("abort", () => reject(new Error("aborted"))))) as typeof fetch);
    vi.useFakeTimers();
    const pending = isAdminAssertion(JWS);
    await vi.advanceTimersByTimeAsync(5100);
    expect(await pending).toBe(false);
    vi.useRealTimers();
  });
});
