import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, DEFAULT_API_URL, STORAGE_KEYS, apiClient, apiUrl, getSettings, hasToken, problemMessage, setSettings, unwrap } from "./client";

afterEach(() => {
  window.localStorage.clear();
  vi.restoreAllMocks();
});

describe("settings", () => {
  it("defaults when nothing is stored", () => {
    expect(getSettings()).toEqual({ token: "", apiUrl: DEFAULT_API_URL });
    expect(hasToken()).toBe(false);
  });

  it("round-trips through localStorage and trims a trailing slash", () => {
    setSettings({ token: "abc", apiUrl: "http://api.example:8000/" });
    expect(window.localStorage.getItem(STORAGE_KEYS.token)).toBe("abc");
    expect(getSettings()).toEqual({ token: "abc", apiUrl: "http://api.example:8000" });
    expect(hasToken()).toBe(true);
    expect(apiUrl("/api/v1/health")).toBe("http://api.example:8000/api/v1/health");
  });
});

describe("apiClient", () => {
  it("sends the bearer token to the configured API URL", async () => {
    setSettings({ token: "secret", apiUrl: "http://api.example:8000" });
    const fetchMock = vi.fn(async (input: Request | string | URL) => {
      const request = input instanceof Request ? input : new Request(input);
      expect(request.url).toBe("http://api.example:8000/api/v1/me");
      expect(request.headers.get("authorization")).toBe("Bearer secret");
      return new Response(JSON.stringify({ email: "test@example.com", user_id: "u" }), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    });
    const client = apiClient({ fetch: fetchMock as unknown as typeof fetch });
    const me = await unwrap(client.GET("/api/v1/me"));
    expect(me.email).toBe("test@example.com");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("turns a problem+json error into ApiError", async () => {
    setSettings({ token: "bad", apiUrl: "http://api.example:8000" });
    const fetchMock = vi.fn(async () =>
      new Response(JSON.stringify({ type: "about:blank", title: "Unauthorized", status: 401, detail: "missing or invalid bearer token" }), {
        status: 401,
        headers: { "content-type": "application/problem+json" },
      }),
    );
    const client = apiClient({ fetch: fetchMock as unknown as typeof fetch });
    await expect(unwrap(client.GET("/api/v1/me"))).rejects.toMatchObject<Partial<ApiError>>({
      status: 401,
      message: "missing or invalid bearer token",
    });
  });

  it("folds the first field errors from a 422 validation problem into the message", async () => {
    setSettings({ token: "bad", apiUrl: "http://api.example:8000" });
    const fetchMock = vi.fn(async () =>
      new Response(
        JSON.stringify({
          type: "about:blank",
          title: "Unprocessable Entity",
          status: 422,
          detail: "request validation failed",
          errors: [
            { loc: ["body", "email"], msg: "field required" },
            { loc: ["body", "age"], msg: "must be positive" },
          ],
        }),
        { status: 422, headers: { "content-type": "application/problem+json" } },
      ),
    );
    const client = apiClient({ fetch: fetchMock as unknown as typeof fetch });
    await expect(unwrap(client.GET("/api/v1/me"))).rejects.toMatchObject<Partial<ApiError>>({
      status: 422,
      message: "request validation failed (body.email: field required; body.age: must be positive)",
    });
  });
});

describe("problemMessage", () => {
  it("falls back to detail (or title) when there are no field errors", () => {
    expect(problemMessage({ title: "Not Found", status: 404, detail: "job not found" })).toBe("job not found");
    expect(problemMessage({ title: "Not Found", status: 404 })).toBe("Not Found");
  });

  it("appends at most the first three field errors", () => {
    const problem = {
      title: "Unprocessable Entity",
      status: 422,
      detail: "request validation failed",
      errors: [
        { loc: ["a"], msg: "1" },
        { loc: ["b"], msg: "2" },
        { loc: ["c"], msg: "3" },
        { loc: ["d"], msg: "4" },
      ],
    };
    expect(problemMessage(problem)).toBe("request validation failed (a: 1; b: 2; c: 3)");
  });
});
