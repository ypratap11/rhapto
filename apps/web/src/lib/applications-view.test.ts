import { describe, expect, it } from "vitest";
import type { ApplicationOut } from "@/lib/api/queries";
import { CHIP_IDS, chipCounts, isApplication, lastChange, rowsForChip, statusWords } from "./applications-view";

const row = (id: string, status: string, updated_at: string, closed_reason: string | null = null, history: { status: string; at: string }[] = []) =>
  ({ id, status, updated_at, closed_reason, status_history: history, job: { id: `j${id}`, company: `Co ${id}`, title: "TPM" } }) as unknown as ApplicationOut;

const rows = [
  row("1", "applied", "2026-10-01T00:00:00Z"),
  row("2", "screen", "2026-10-02T00:00:00Z"),
  row("3", "interview", "2026-10-03T00:00:00Z"),
  row("4", "offer", "2026-10-04T00:00:00Z"),
  row("5", "closed", "2026-10-05T00:00:00Z", "rejected"),
  row("6", "closed", "2026-10-06T00:00:00Z", "filled"),
  row("7", "closed", "2026-10-07T00:00:00Z"),
];

describe("applications view", () => {
  it("orders the chips Applied, Interviewing, Offer, Closed, All", () => {
    expect([...CHIP_IDS]).toEqual(["applied", "interviewing", "offer", "closed", "all"]);
  });

  it("counts screen under Applied", () => {
    expect(chipCounts(rows)).toEqual({ applied: 2, interviewing: 1, offer: 1, closed: 3, all: 7 });
  });

  it("filters newest change first", () => {
    expect(rowsForChip(rows, "applied").map((r) => r.id)).toEqual(["2", "1"]);
    expect(rowsForChip(rows, "all").map((r) => r.id)).toEqual(["7", "6", "5", "4", "3", "2", "1"]);
  });

  it("dates a row by its last status change, not by a notes edit", () => {
    const edited = row("8", "applied", "2026-10-09T00:00:00Z", null, [
      { status: "applied", at: "2026-10-01T00:00:00Z" },
      { status: "interview", at: "2026-10-03T00:00:00Z" },
    ]);
    expect(lastChange(edited)).toBe("2026-10-03T00:00:00Z");
    expect(lastChange(row("9", "applied", "2026-10-02T00:00:00Z"))).toBe("2026-10-02T00:00:00Z");
  });

  it("does not treat discovered or queued as applications", () => {
    expect(isApplication(row("a", "discovered", "x"))).toBe(false);
    expect(isApplication(row("b", "queued", "x"))).toBe(false);
    expect(isApplication(row("c", "screen", "x"))).toBe(true);
    expect(isApplication(row("d", "constructor", "x"))).toBe(false);
  });

  it("says the closed reason in words", () => {
    expect(statusWords(rows[4]!)).toBe("Rejected");
    expect(statusWords(rows[5]!)).toBe("Position filled");
    expect(statusWords(rows[6]!)).toBe("Closed");
    expect(statusWords(rows[1]!)).toBe("Screening");
    expect(statusWords(rows[2]!)).toBe("Interviewing");
  });
});
