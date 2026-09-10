import { describe, expect, it } from "vitest";
import type { ApplicationOut, BoardOut } from "@/lib/api/queries";
import { findColumn, moveCard, normalizeColumns } from "./board";

function app(id: string, status: string): ApplicationOut {
  return {
    id,
    job: { id: `job-${id}`, company: "ExampleCo", title: "PM" },
    package_id: null,
    status,
    applied_at: null,
    notes: "",
    status_history: [],
    created_at: "2026-09-09T10:00:00Z",
    updated_at: "2026-09-09T10:00:00Z",
  } as ApplicationOut;
}

const board: BoardOut = { columns: { queued: [app("a", "queued"), app("b", "queued")], applied: [app("c", "applied")], weird: [app("z", "weird")] } } as unknown as BoardOut;

describe("board", () => {
  it("normalizes to all seven columns and drops unknown statuses", () => {
    const columns = normalizeColumns(board);
    expect(Object.keys(columns)).toEqual(["discovered", "queued", "applied", "screen", "interview", "offer", "closed"]);
    expect(columns.queued.map((a) => a.id)).toEqual(["a", "b"]);
    expect(columns.discovered).toEqual([]);
  });
  it("moves a card to the top of the target column and updates its status", () => {
    const columns = normalizeColumns(board);
    const next = moveCard(columns, "b", "applied");
    expect(next.queued.map((a) => a.id)).toEqual(["a"]);
    expect(next.applied.map((a) => a.id)).toEqual(["b", "c"]);
    expect(next.applied[0]!.status).toBe("applied");
    expect(findColumn(next, "b")).toBe("applied");
  });
  it("is a no-op for unknown ids or same column", () => {
    const columns = normalizeColumns(board);
    expect(moveCard(columns, "nope", "applied")).toBe(columns);
    expect(moveCard(columns, "a", "queued")).toBe(columns);
  });
});
