import { afterEach, describe, expect, it, vi } from "vitest";
import { freeLimitLine, freeRuns, pricingLine } from "./copy";

afterEach(() => vi.unstubAllEnvs());

describe("free-run copy follows the build-time cap", () => {
  it("names the number when the cap is positive", () => {
    vi.stubEnv("NEXT_PUBLIC_TRIAL_RUNS", "5");
    expect(freeRuns()).toBe(5);
    expect(freeLimitLine(true)).toBe("Free during the beta: your first resume import and 5 AI runs are on us, then you use your own AI key.");
    expect(pricingLine(true)).toMatch(/5 AI runs on us \(your first resume import is free\)/);
    vi.stubEnv("NEXT_PUBLIC_TRIAL_RUNS", "3");
    expect(freeLimitLine(true)).toMatch(/3 AI runs/);
  });
  it("0 means bring your own key and promises no free run", () => {
    vi.stubEnv("NEXT_PUBLIC_TRIAL_RUNS", "0");
    expect(freeRuns()).toBeNull();
    expect(freeLimitLine(true)).toBe("Bring your own AI key to use Rhapto.");
    expect(pricingLine(true)).not.toMatch(/\d|free/i);
  });
  it.each(["-1", "", "abc", "2.5"])("%j names no number", (value) => {
    vi.stubEnv("NEXT_PUBLIC_TRIAL_RUNS", value);
    expect(freeRuns()).toBeNull();
    expect(freeLimitLine(true)).toMatch(/a few AI runs/);
    expect(freeLimitLine(true)).not.toMatch(/\d/);
  });
  it("unset names no number", () => {
    vi.stubEnv("NEXT_PUBLIC_TRIAL_RUNS", undefined as unknown as string);
    expect(freeRuns()).toBeNull();
    expect(pricingLine(true)).toMatch(/a few AI runs/);
  });
  it("token mode never mentions free runs", () => {
    vi.stubEnv("NEXT_PUBLIC_TRIAL_RUNS", "5");
    expect(freeLimitLine(false)).toBe("Free and open source (AGPL-3.0); you use your own AI key.");
    expect(pricingLine(false)).toBe("Free and open source (AGPL-3.0); you use your own AI key.");
  });
});
