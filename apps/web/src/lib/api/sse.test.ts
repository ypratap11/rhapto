import { afterEach, describe, expect, it, vi } from "vitest";
import { parseSseChunk, readTaskEvents } from "./sse";
import { setSettings } from "./client";

afterEach(() => {
  window.localStorage.clear();
  vi.restoreAllMocks();
});

describe("parseSseChunk", () => {
  it("parses complete blocks and keeps the remainder", () => {
    const raw = ': ping\n\nevent: state\ndata: {"status":"running"}\n\nevent: progress\ndata: {"event":"progress","step":"extract"}\n\nevent: done\ndata: {"ev';
    const { events, rest } = parseSseChunk(raw);
    expect(events).toEqual([
      { event: "state", data: { status: "running" } },
      { event: "progress", data: { event: "progress", step: "extract" } },
    ]);
    expect(rest).toBe('event: done\ndata: {"ev');
  });

  it("handles CRLF framing and multi-line data", () => {
    const { events } = parseSseChunk('event: done\r\ndata: {"a":\r\ndata: 1}\r\n\r\n');
    expect(events).toEqual([{ event: "done", data: { a: 1 } }]);
  });
});

describe("readTaskEvents", () => {
  function streamOf(chunks: string[]): ReadableStream<Uint8Array> {
    const encoder = new TextEncoder();
    return new ReadableStream({
      start(controller) {
        for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
        controller.close();
      },
    });
  }

  it("streams events with the bearer header and stops after done", async () => {
    setSettings({ token: "tok", apiUrl: "http://api.example:8000" });
    const fetchMock = vi.fn(async (input: Request | string | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      expect(url).toBe("http://api.example:8000/api/v1/tasks/t1/events");
      expect(new Headers(init?.headers).get("authorization")).toBe("Bearer tok");
      return new Response(
        streamOf(['event: state\ndata: {"status":"running"}\n\n', 'event: progress\ndata: {"event":"progress","step":"extract"}\n\nevent: done\ndata: {"event":"done","package_id":"p"}\n\n', 'event: progress\ndata: {"step":"should not be seen"}\n\n']),
        { status: 200, headers: { "content-type": "text/event-stream" } },
      );
    });
    vi.stubGlobal("fetch", fetchMock);
    const seen: string[] = [];
    await readTaskEvents("t1", (e) => seen.push(e.event));
    expect(seen).toEqual(["state", "progress", "done"]);
  });

  it("throws ApiError on a non-2xx response", async () => {
    setSettings({ token: "tok", apiUrl: "http://api.example:8000" });
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({ title: "Not Found", status: 404 }), { status: 404, headers: { "content-type": "application/problem+json" } })),
    );
    await expect(readTaskEvents("missing", () => undefined)).rejects.toMatchObject({ status: 404 });
  });
});
