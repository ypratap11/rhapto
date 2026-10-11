import { describe, expect, it } from "vitest";
import { resolveTab } from "./resumes-tab";

describe("resolveTab", () => {
  it.each([
    ["tab=review", "review"],
    ["tab=ready", "ready"],
    ["tab=blocked", "blocked"],
    ["tab=applied", "review"],
    ["filter=all", "review"],
    ["tab=junk", "review"],
    ["", "review"],
    ["filter=blocked", "blocked"],
  ])("resolveTab(%s)", (q, want) => expect(resolveTab(new URLSearchParams(q))).toBe(want));
});
