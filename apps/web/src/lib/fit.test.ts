import { describe, expect, it } from "vitest";
import { SOURCE_LABEL } from "./fit";

describe("fit helpers", () => {
  it("labels sources", () => {
    expect(SOURCE_LABEL["hn-hiring"]).toBe("HN");
  });
});
