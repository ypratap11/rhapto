import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { startTailoring, stopTailoring, useTailoringCount } from "./tailoring";

describe("tailoring", () => {
  it("goes 0 -> 1 -> 0 across start/stop and re-renders the hook", () => {
    const { result } = renderHook(() => useTailoringCount());
    expect(result.current).toBe(0);

    act(() => startTailoring("j1"));
    expect(result.current).toBe(1);

    act(() => stopTailoring("j1"));
    expect(result.current).toBe(0);
  });

  it("leaves a count of 1 when two starts are followed by a single stop", () => {
    const { result } = renderHook(() => useTailoringCount());

    act(() => startTailoring("j1"));
    act(() => startTailoring("j2"));
    expect(result.current).toBe(2);

    act(() => stopTailoring("j1"));
    expect(result.current).toBe(1);

    // Clean up so other tests in this file see a fresh module-level store.
    act(() => stopTailoring("j2"));
  });
});
