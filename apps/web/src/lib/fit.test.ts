import { describe, expect, it } from "vitest";
import { fitTone, formatFit, SOURCE_LABEL } from "./fit";

describe("fit helpers", () => {
  it("maps fit to tones by band and threshold", () => {
    expect(fitTone(80, 60)).toBe("green");
    expect(fitTone(65, 60)).toBe("amber");
    expect(fitTone(59, 60)).toBe("slate");
    expect(fitTone(null, 60)).toBe("slate");
    expect(fitTone(70, null)).toBe("slate");
  });
  it("formats missing fit as a dash and labels sources", () => {
    expect(formatFit(null)).toBe("—");
    expect(formatFit(72)).toBe("72");
    expect(SOURCE_LABEL["hn-hiring"]).toBe("HN");
  });
});
