import { describe, expect, it } from "vitest";
import { contrast, evaluate, mixHex, parseThemes, readCss } from "./contrast.mjs";

const css = readCss();

function failures(source: string) {
  const { rows } = evaluate(source);
  return rows.filter((r) => !r.pass).map((r) => `${r.theme}: --${r.pair.fg} on --${r.pair.bg} (${r.pair.label}) ${r.ratio.toFixed(2)}`);
}

/** True if some failing row in `theme` has `label` as its pair label. Match on the label, not the token prefix:
 * the two chip pairs also have fg `primary` on `surface`/`background`; they are tinted and DO fail at #c8401f. */
function failsOn(found: string[], theme: string, label: string) {
  return found.some((f) => f.startsWith(`${theme}:`) && f.includes(`(${label})`));
}

describe("design tokens meet WCAG AA", () => {
  it("has every token the pair list needs, in both themes", () => {
    expect(evaluate(css).missing).toEqual([]);
  });

  it("passes every pair in both themes", () => {
    expect(failures(css)).toEqual([]);
  });

  it("resolves var() tokens: --glow-to is --background", () => {
    const { light, dark } = parseThemes(css);
    expect(light["glow-to"]).toBe(light["background"]);
    expect(dark["glow-to"]).toBe(dark["background"]);
  });
});

describe("the checker itself", () => {
  it("computes known ratios", () => {
    expect(contrast("#000000", "#ffffff")).toBeCloseTo(21, 1);
    expect(contrast("#ffffff", "#b63a1c")).toBeCloseTo(5.82, 1);
    expect(mixHex("#000000", 0.5, "#ffffff")).toBe("#808080");
  });

  it("FAILS on the known-bad primary #c8401f, and only on tinted surfaces", () => {
    const bad = css.replace(/(:root\s*\{[\s\S]*?--primary:\s*)#[0-9a-fA-F]{6}/, "$1#c8401f");
    expect(bad).not.toBe(css); // the replacement really happened
    const found = failures(bad);
    expect(failsOn(found, "light", "primary text on surface-muted")).toBe(true);
    // The chips are tinted surfaces too, and fail (4.33 over a card, 4.10 over the page).
    expect(failsOn(found, "light", "primary chip (10% primary over a card)")).toBe(true);
    expect(failsOn(found, "light", "primary chip (10% primary over the page)")).toBe(true);
    // Plain surfaces still pass at #c8401f, which is exactly why a plain-background check misses it.
    expect(failsOn(found, "light", "primary text on background")).toBe(false);
    expect(failsOn(found, "light", "primary text on surface")).toBe(false);
  });

  it("FAILS on today's text-on-band link colour (primary #b4432e on peach is 4.47)", () => {
    const old = css.replace(/(:root\s*\{[\s\S]*?--primary:\s*)#[0-9a-fA-F]{6}/, "$1#b4432e");
    expect(failsOn(failures(old), "light", "primary text on band-peach")).toBe(true);
  });

  it("reports a pair whose token is missing instead of skipping it", () => {
    const stripped = css.replace(/--link-on-band:[^;]*;/g, "");
    expect(evaluate(stripped).missing.length).toBeGreaterThan(0);
  });
});
