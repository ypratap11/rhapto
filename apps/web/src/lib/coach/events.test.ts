import { afterEach, describe, expect, it, vi } from "vitest";
import { setSettings } from "@/lib/api/client";
import { fireCoachEvent } from "./events";

afterEach(() => vi.unstubAllGlobals());

describe("fireCoachEvent", () => {
  it("posts only the step name, authenticated", async () => {
    setSettings({ token: "tok", apiUrl: "http://localhost:8000" });
    const fetchMock = vi.fn(async () => new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);
    await fireCoachEvent("jobs_shown");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("http://localhost:8000/api/v1/coach/events");
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toEqual({ step: "jobs_shown" });
    expect(new Headers(init.headers).get("authorization")).toBe("Bearer tok");
  });

  it("never rejects: a network error and a 500 are both swallowed", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("offline"); }));
    await expect(fireCoachEvent("started")).resolves.toBeUndefined();
    vi.stubGlobal("fetch", vi.fn(async () => new Response("boom", { status: 500 })));
    await expect(fireCoachEvent("started")).resolves.toBeUndefined();
  });
});
