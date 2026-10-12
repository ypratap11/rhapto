import { describe, expect, it } from "vitest";
import { formatCostUsd, formatDate, formatDaysAgo, formatRelative, formatSalary, formatTokens, truncate, USD_SOURCES } from "./format";

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

describe("formatSalary", () => {
  const cases: [string | null | undefined, string, string | null][] = [
    ["187835-187835", "adzuna", "$187,835"], ["150000-190000", "adzuna", "$150k–$190k"], ["187835", "adzuna", "$187,835"],
    ["150500-190000", "adzuna", "$150,500–$190,000"], ["187835", "jsearch", "187,835"], ["150000-190000", "jsearch", "150k–190k"],
    ["$120k - $160k", "adzuna", "$120k - $160k"], ["£50,000", "adzuna", "£50,000"], ["Competitive", "jooble", "Competitive"],
    ["-", "adzuna", "-"], ["abc-def", "adzuna", "abc-def"], ["0", "adzuna", "0"], ["999-1000", "adzuna", "999-1000"],
    ["190000-150000", "adzuna", "$150k–$190k"], ["0150000", "adzuna", "0150000"],
    ["1000000", "adzuna", "1000000"], ["", "adzuna", null], [null, "adzuna", null], [undefined, "adzuna", null], ["  ", "adzuna", null],
  ];
  it.each(cases)("formatSalary(%s,%s)", (raw, src, want) => expect(formatSalary(raw, src)).toBe(want));
  it("treats only adzuna as USD", () => {
    expect([...USD_SOURCES]).toEqual(["adzuna"]);
  });
});

describe("formatDaysAgo", () => {
  const now = new Date("2026-10-11T12:00:00Z");
  const ago = (days: number, extraHours = 0) => new Date(now.getTime() - (days * 24 + extraHours) * 3_600_000).toISOString();
  it("says today, yesterday, then days", () => {
    expect(formatDaysAgo(ago(0, 5), now)).toBe("today");
    expect(formatDaysAgo(ago(1, 1), now)).toBe("yesterday");
    expect(formatDaysAgo(ago(12), now)).toBe("12 days ago");
  });
  it("moves to months after about two months", () => {
    expect(formatDaysAgo(ago(59), now)).toBe("59 days ago");
    expect(formatDaysAgo(ago(75), now)).toBe("2 months ago");
  });
  it("treats a date in the future as today", () => {
    expect(formatDaysAgo(ago(-2), now)).toBe("today");
  });
});
