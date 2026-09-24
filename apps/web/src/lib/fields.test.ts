import { describe, expect, it } from "vitest";
import { fieldsWithTracks } from "./fields";

const ALL = [
  { id: "program-project-management", name: "Program & Project Management" },
  { id: "engineering", name: "Engineering" },
  { id: "design", name: "Design" },
];

describe("fieldsWithTracks", () => {
  it("offers only fields the user has a track in", () => {
    // The bug this exists for: three tracks all in one field, twelve fields offered, eleven of
    // which return an empty list that is indistinguishable from "nothing matches right now".
    const tracks = [
      { field: "program-project-management" },
      { field: "program-project-management" },
    ];
    expect(fieldsWithTracks(ALL, tracks).map((f) => f.id)).toEqual(["program-project-management"]);
  });

  it("keeps every field a track covers, without duplicating one", () => {
    const tracks = [{ field: "engineering" }, { field: "design" }, { field: "engineering" }];
    expect(fieldsWithTracks(ALL, tracks).map((f) => f.id)).toEqual(["engineering", "design"]);
  });

  it("ignores tracks with no taxonomy yet", () => {
    // `field` is nullable: a track created before the taxonomy existed has none, and it must not
    // contribute a filter that cannot match.
    const tracks = [{ field: null }, { field: undefined }, { field: "design" }];
    expect(fieldsWithTracks(ALL, tracks).map((f) => f.id)).toEqual(["design"]);
  });

  it("returns nothing when the user has no tracks at all", () => {
    expect(fieldsWithTracks(ALL, [])).toEqual([]);
  });

  it("shows the full list while tracks are still loading", () => {
    // Undefined is "not known yet", not "none" — collapsing the control to empty on every page
    // load and then repopulating it would read as a flicker, not as a filter.
    expect(fieldsWithTracks(ALL, undefined).map((f) => f.id)).toEqual(ALL.map((f) => f.id));
  });
});
