import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { applyOpenedAt, clearApplyOpened, markApplyOpened, useApplyPrompt } from "./apply-prompt";

afterEach(() => localStorage.clear());

describe("apply prompt", () => {
  it("remembers, per job, that the posting was opened", () => {
    markApplyOpened("j1");
    expect(applyOpenedAt("j1")).not.toBeNull();
    expect(applyOpenedAt("j2")).toBeNull();
    clearApplyOpened("j1");
    expect(applyOpenedAt("j1")).toBeNull();
  });

  it("asks only after the tab comes back, and only for the job that was opened", () => {
    const { result } = renderHook(() => useApplyPrompt("j1"));
    expect(result.current).toBe(false);

    act(() => markApplyOpened("j1"));
    expect(result.current).toBe(false); // still on the employer's tab

    act(() => {
      window.dispatchEvent(new Event("focus"));
    });
    expect(result.current).toBe(true);

    act(() => clearApplyOpened("j1"));
    expect(result.current).toBe(false);
  });
});
