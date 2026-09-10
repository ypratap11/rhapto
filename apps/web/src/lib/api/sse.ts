import { ApiError, apiUrl, authHeaders, type Problem } from "./client";

export type TaskEventName = "state" | "progress" | "done" | "error";
export type TaskEvent = { event: TaskEventName; data: Record<string, unknown> };

const TERMINAL: ReadonlySet<string> = new Set(["done", "error"]);

export function parseSseChunk(buffer: string): { events: TaskEvent[]; rest: string } {
  const normalized = buffer.replace(/\r\n/g, "\n");
  const blocks = normalized.split("\n\n");
  const rest = blocks.pop() ?? "";
  const events: TaskEvent[] = [];
  for (const block of blocks) {
    let event = "message";
    const dataLines: string[] = [];
    for (const line of block.split("\n")) {
      if (line.startsWith(":") || line.trim() === "") continue;
      const idx = line.indexOf(":");
      const field = idx === -1 ? line : line.slice(0, idx);
      const value = idx === -1 ? "" : line.slice(idx + 1).replace(/^ /, "");
      if (field === "event") event = value;
      else if (field === "data") dataLines.push(value);
    }
    if (dataLines.length === 0) continue;
    let data: Record<string, unknown>;
    try {
      data = JSON.parse(dataLines.join("\n")) as Record<string, unknown>;
    } catch {
      data = { raw: dataLines.join("\n") };
    }
    events.push({ event: event as TaskEventName, data });
  }
  return { events, rest };
}

export async function readTaskEvents(taskId: string, onEvent: (event: TaskEvent) => void, signal?: AbortSignal): Promise<void> {
  const response = await fetch(apiUrl(`/api/v1/tasks/${taskId}/events`), {
    headers: { Accept: "text/event-stream", ...authHeaders() },
    signal,
  });
  if (!response.ok) {
    let problem: Problem | null = null;
    try {
      problem = (await response.json()) as Problem;
    } catch {
      problem = null;
    }
    throw new ApiError(response.status, problem, `HTTP ${response.status}`);
  }
  if (!response.body) return;
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parsed = parseSseChunk(buffer);
      buffer = parsed.rest;
      for (const event of parsed.events) {
        onEvent(event);
        if (TERMINAL.has(event.event)) {
          await reader.cancel();
          return;
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}
