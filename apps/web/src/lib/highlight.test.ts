import { describe, expect, it } from "vitest";
import { highlightTerms } from "./highlight";

describe("highlightTerms", () => {
  it("marks whole-word, case-insensitive hits without overlaps", () => {
    const segments = highlightTerms("Lead the Snowflake migration; snowflakes are not migrations.", ["snowflake migration", "Snowflake", "lead"]);
    expect(segments).toEqual([
      { text: "Lead", hit: true },
      { text: " the ", hit: false },
      { text: "Snowflake migration", hit: true },
      { text: "; snowflakes are not migrations.", hit: false },
    ]);
  });
  it("escapes regex characters and ignores empty terms", () => {
    expect(highlightTerms("C++ and C# (senior)", ["C++", "", "(senior)"])).toEqual([
      { text: "C++", hit: true },
      { text: " and C# ", hit: false },
      { text: "(senior)", hit: true },
    ]);
  });
  it("returns the whole text when there are no terms", () => {
    expect(highlightTerms("plain", [])).toEqual([{ text: "plain", hit: false }]);
  });
});
