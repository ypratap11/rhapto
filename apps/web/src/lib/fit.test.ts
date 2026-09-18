import { describe, expect, it } from "vitest";
import { fitTone, formatFit, SOURCE_LABEL } from "./fit";

describe("fit helpers", () => {
  it("maps fit to tones by band and threshold", () => {
    expect(fitTone(80, 60)).toBe("high");
    expect(fitTone(65, 60)).toBe("mid");
    expect(fitTone(59, 60)).toBe("neutral");
    expect(fitTone(null, 60)).toBe("neutral");
    expect(fitTone(70, null)).toBe("neutral");
  });
  it("formats missing fit as a dash and labels sources", () => {
    expect(formatFit(null)).toBe("—");
    expect(formatFit(72)).toBe("72");
    expect(SOURCE_LABEL["hn-hiring"]).toBe("HN");
  });
});
