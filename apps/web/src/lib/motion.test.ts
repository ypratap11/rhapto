import { renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { usePrefersReducedMotion } from "./motion";

const setMedia = (value: unknown) => Object.defineProperty(window, "matchMedia", { configurable: true, writable: true, value });
afterEach(() => Reflect.deleteProperty(window, "matchMedia"));

describe("usePrefersReducedMotion", () => {
  it("reads the media query on the client", () => {
    setMedia((q: string) => ({ matches: true, media: q, addEventListener() {}, removeEventListener() {} }));
    expect(renderHook(() => usePrefersReducedMotion()).result.current).toBe(true);
    setMedia((q: string) => ({ matches: false, media: q, addEventListener() {}, removeEventListener() {} }));
    expect(renderHook(() => usePrefersReducedMotion()).result.current).toBe(false);
  });

  it("is false (nothing to reduce) where matchMedia does not exist", () => {
    expect(renderHook(() => usePrefersReducedMotion()).result.current).toBe(false);
  });

  it("follows a change event", async () => {
    let listener: () => void = () => {};
    let matches = false;
    setMedia((q: string) => ({
      get matches() { return matches; },
      media: q,
      addEventListener: (_: string, l: () => void) => { listener = l; },
      removeEventListener() {},
    }));
    const { result, rerender } = renderHook(() => usePrefersReducedMotion());
    expect(result.current).toBe(false);
    matches = true;
    listener();
    rerender();
    expect(result.current).toBe(true);
  });
});
