import { describe, expect, it } from "vitest";
import { formatCostUsd, formatDate, formatRelative, formatTokens, truncate } from "./format";

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
  it("formats token counts with thousands separators", () => {
    expect(formatTokens(0)).toBe("0");
    expect(formatTokens(1234567)).toBe("1,234,567");
  });
  it("formats a USD cost, flooring tiny non-zero amounts to a legible minimum", () => {
    expect(formatCostUsd(0)).toBe("$0.00");
    expect(formatCostUsd(12.3)).toBe("$12.30");
    expect(formatCostUsd(0.0004)).toBe("<$0.01");
  });
});
