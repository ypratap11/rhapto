import { describe, expect, it } from "vitest";
import { datelessBlocks, isDateless } from "./blocks";

/** The same three-block fixture the API test uses (`tests/api/test_checklist_setup_api.py`): two
 * with no period at all and one whose period is whitespace. Both sides must count 3, because the
 * dashboard's "N need a period" row deep-links into the tab this filter drives — a disagreement
 * would send the user to a screen with nothing to fix. */
const blocks = [
  { id: "a", period: null },
  { id: "b", period: undefined },
  { id: "c", period: "   " },
  { id: "d", period: "2020-2021" },
  { id: "e", period: "2019" },
];

describe("isDateless", () => {
  it("counts a missing, null, empty and whitespace-only period as dateless", () => {
    expect(isDateless({ period: null })).toBe(true);
    expect(isDateless({})).toBe(true);
    expect(isDateless({ period: "" })).toBe(true);
    // The case a bare `!b.period` misses and the API's `btrim` catches. `resume_blocks.period` is
    // nullable free text, so an older import or a hand-written row can hold exactly this.
    expect(isDateless({ period: "   " })).toBe(true);
    expect(isDateless({ period: "\t\n" })).toBe(true);
  });

  it("does not count a real period as dateless", () => {
    expect(isDateless({ period: "2020-2021" })).toBe(false);
    expect(isDateless({ period: "2019" })).toBe(false);
    expect(isDateless({ period: " 2019 " })).toBe(false);
  });
});

describe("datelessBlocks", () => {
  it("agrees with the API's count on the shared fixture", () => {
    expect(datelessBlocks(blocks)).toHaveLength(3);
    expect(datelessBlocks(blocks).map((b) => b.id)).toEqual(["a", "b", "c"]);
  });

  it("returns nothing when every block has a period", () => {
    expect(datelessBlocks(blocks.filter((b) => !isDateless(b)))).toEqual([]);
  });
});
