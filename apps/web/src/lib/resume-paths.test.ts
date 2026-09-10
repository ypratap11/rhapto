import { describe, expect, it } from "vitest";
import { bulletPath, entryPath, fieldPath, parsePath, summaryPath } from "./resume-paths";

describe("resume paths", () => {
  it("builds and parses paths", () => {
    expect(summaryPath(1)).toBe("summary[1]");
    expect(entryPath(0, 2)).toBe("sections[0].entries[2]");
    expect(bulletPath(0, 2, 3)).toBe("sections[0].entries[2].bullets[3]");
    expect(fieldPath(1, 0, "title")).toBe("sections[1].entries[0].title");
    expect(parsePath("summary[1]")).toEqual({ kind: "summary", index: 1 });
    expect(parsePath("sections[0].entries[2]")).toEqual({ kind: "entry", section: 0, entry: 2 });
    expect(parsePath("sections[0].entries[2].bullets[3]")).toEqual({ kind: "bullet", section: 0, entry: 2, bullet: 3 });
    expect(parsePath("sections[1].entries[0].title")).toEqual({ kind: "field", section: 1, entry: 0, field: "title" });
    expect(parsePath("cover_note")).toEqual({ kind: "cover_note" });
    expect(parsePath("nonsense")).toEqual({ kind: "unknown", raw: "nonsense" });
  });
});
