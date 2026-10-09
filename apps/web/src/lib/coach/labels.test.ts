import { describe, expect, it } from "vitest";
import { matchLabel, runsLeftLine } from "./labels";

describe("matchLabel", () => {
  it("is Strong at or above the track's min_fit, otherwise Good, never a number", () => {
    expect(matchLabel(60, 60)).toBe("Strong match");
    expect(matchLabel(88, 60)).toBe("Strong match");
    expect(matchLabel(59, 60)).toBe("Good match");
    expect(matchLabel(46, 60)).toBe("Good match");
    expect(matchLabel(null, 60)).toBe("Good match");
    expect(matchLabel(undefined, 60)).toBe("Good match");
  });
});

describe("runsLeftLine", () => {
  it("shows runs left only when a cap applies", () => {
    expect(runsLeftLine(null)).toBeNull();
    expect(runsLeftLine(undefined)).toBeNull();
    expect(runsLeftLine(3)).toBe("3 free runs left");
    expect(runsLeftLine(1)).toBe("1 free run left");
    expect(runsLeftLine(0)).toBe("No free runs left. Add your own AI key in Settings to keep going.");
  });
});
