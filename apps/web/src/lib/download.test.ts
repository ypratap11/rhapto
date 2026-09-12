import { afterEach, describe, expect, it, vi } from "vitest";
import { setSettings } from "./api/client";
import { downloadAuthenticated, resumeFilename } from "./download";

afterEach(() => {
  window.localStorage.clear();
  vi.restoreAllMocks();
  vi.useRealTimers();
});

describe("downloadAuthenticated", () => {
  it("sends the bearer token only to the configured API URL", async () => {
    setSettings({ token: "secret", apiUrl: "http://api.example:8000" });
    const fetchMock = vi.fn(async (input: Request | string | URL, init?: RequestInit) => {
      const request = input instanceof Request ? input : new Request(input, init);
      expect(request.url).toBe("http://api.example:8000/api/v1/profile/export");
      expect(request.headers.get("authorization")).toBe("Bearer secret");
      return new Response("zip bytes", { status: 200 });
    });
    vi.stubGlobal("fetch", fetchMock);
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    const createObjectURL = vi.fn(() => "blob:mock-url");
    const revokeObjectURL = vi.fn();
    vi.stubGlobal("URL", Object.assign(URL, { createObjectURL, revokeObjectURL }));

    await downloadAuthenticated("/api/v1/profile/export", "profile.zip");

    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("defers revoking the object URL instead of doing it synchronously after click", async () => {
    vi.useFakeTimers();
    setSettings({ token: "secret", apiUrl: "http://api.example:8000" });
    const fetchMock = vi.fn(async () => new Response("zip bytes", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    const createObjectURL = vi.fn(() => "blob:mock-url");
    const revokeObjectURL = vi.fn();
    vi.stubGlobal("URL", Object.assign(URL, { createObjectURL, revokeObjectURL }));

    await downloadAuthenticated("/api/v1/profile/export", "profile.zip");

    expect(revokeObjectURL).not.toHaveBeenCalled();
    vi.runAllTimers();
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:mock-url");
  });

  it("throws an ApiError with the problem detail on a non-ok response", async () => {
    setSettings({ token: "secret", apiUrl: "http://api.example:8000" });
    const fetchMock = vi.fn(async () =>
      new Response(JSON.stringify({ title: "Not Found", status: 404, detail: "no such export" }), {
        status: 404,
        headers: { "content-type": "application/problem+json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(downloadAuthenticated("/api/v1/profile/export", "profile.zip")).rejects.toMatchObject({
      status: 404,
      message: "no such export",
    });
  });
});

describe("resumeFilename", () => {
  it("builds a filename from the candidate name and kind", () => {
    expect(resumeFilename("Maya Chen", "pdf")).toBe("Maya_Chen_Resume.pdf");
  });

  it("falls back to Resume when the name is blank", () => {
    expect(resumeFilename("", "zip")).toBe("Resume_Package.zip");
  });

  it("strips accents and punctuation down to ASCII underscores", () => {
    expect(resumeFilename("  Ana-María  ", "docx")).toBe("Ana_Mar_a_Resume.docx");
  });
});
