import { describe, expect, it } from "vitest";
import { formatDate, formatRelative, truncate } from "./format";

describe("format", () => {
  it("formats dates", () => {
    expect(formatDate("2026-09-09T10:00:00Z")).toBe("9 Sep 2026");
  });
  it("formats relative time", () => {
    const now = new Date("2026-09-09T12:00:00Z");
    expect(formatRelative("2026-09-09T09:00:00Z", now)).toBe("3h ago");
    expect(formatRelative("2026-09-09T11:59:30Z", now)).toBe("just now");
    expect(formatRelative("2026-09-06T12:00:00Z", now)).toBe("3d ago");
  });
  it("truncates", () => {
    expect(truncate("abcdef", 4)).toBe("abc…");
    expect(truncate("abc", 4)).toBe("abc");
  });
});
