import { existsSync } from "node:fs";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const JWS = "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ1c2VyQGV4YW1wbGUuY29tIn0.c2lnbmF0dXJl";
const NOT_FOUND = new Error("NEXT_NOT_FOUND");
const headerValues: { assertion: string | null } = { assertion: JWS };

vi.mock("next/headers", () => ({
  headers: async () => new Headers(headerValues.assertion === null ? {} : { "cf-access-jwt-assertion": headerValues.assertion }),
}));
vi.mock("next/navigation", () => ({
  notFound: () => {
    throw NOT_FOUND;
  },
}));

import AdminLayout from "./layout";

const child = "child";
let fetchSpy: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  headerValues.assertion = JWS;
  fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("{}", { status: 200 }));
});
afterEach(() => fetchSpy.mockRestore());

describe("admin layout gate", () => {
  it("calls notFound when the assertion is missing", async () => {
    headerValues.assertion = null;
    await expect(AdminLayout({ children: child })).rejects.toBe(NOT_FOUND);
    expect(fetchSpy).not.toHaveBeenCalled();
  });
  it("calls notFound when the assertion is malformed", async () => {
    headerValues.assertion = "not a jws, " + JWS;
    await expect(AdminLayout({ children: child })).rejects.toBe(NOT_FOUND);
    expect(fetchSpy).not.toHaveBeenCalled();
  });
  it("calls notFound when the API returns 404", async () => {
    fetchSpy.mockResolvedValue(new Response("{}", { status: 404 }));
    await expect(AdminLayout({ children: child })).rejects.toBe(NOT_FOUND);
  });
  it("calls notFound when the API returns 503", async () => {
    fetchSpy.mockResolvedValue(new Response("{}", { status: 503 }));
    await expect(AdminLayout({ children: child })).rejects.toBe(NOT_FOUND);
  });
  it("calls notFound when fetch throws", async () => {
    fetchSpy.mockRejectedValue(new TypeError("network"));
    await expect(AdminLayout({ children: child })).rejects.toBe(NOT_FOUND);
  });
  it("renders children when the API returns 200", async () => {
    const out = await AdminLayout({ children: child });
    expect(JSON.stringify(out)).toContain(child);
  });
  it("forwards the assertion and no cookie", async () => {
    await AdminLayout({ children: child });
    const [url, init] = fetchSpy.mock.calls[0] as [string, RequestInit];
    expect(String(url)).toMatch(/\/api\/v1\/admin\/session$/);
    const h = new Headers(init.headers);
    expect(h.get("Cf-Access-Jwt-Assertion")).toBe(JWS);
    expect(h.has("cookie")).toBe(false);
    expect(h.has("authorization")).toBe(false);
  });
  it("does not cache", async () => {
    await AdminLayout({ children: child });
    const [, init] = fetchSpy.mock.calls[0] as [string, RequestInit];
    expect(init.cache).toBe("no-store");
  });
  it("app/admin contains no loading.tsx", () => {
    for (const f of ["loading.tsx", "loading.ts", "loading.jsx", "loading.js"]) {
      expect(existsSync(join(import.meta.dirname, f))).toBe(false);
    }
  });
});
