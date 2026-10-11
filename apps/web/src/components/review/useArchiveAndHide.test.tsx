import { renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const calls: string[] = [];
const archive = vi.fn(async (id: string) => void calls.push(`archive:${id}`));
const hide = vi.fn(async (id: string) => void calls.push(`hide:${id}`));
const unhide = vi.fn(async (id: string) => void calls.push(`unhide:${id}`));
vi.mock("@/lib/api/queries", () => ({
  useArchivePackage: () => ({ mutateAsync: archive, isPending: false }),
  useHideJob: () => ({ mutateAsync: hide, isPending: false }),
  useUnhideJob: () => ({ mutateAsync: unhide, isPending: false }),
}));
const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast }));

import { useArchiveAndHide } from "./useArchiveAndHide";

const args = { packageId: "p1", jobId: "j1", label: "ExampleCo · TPM" };

describe("useArchiveAndHide", () => {
  beforeEach(() => {
    calls.length = 0;
    vi.clearAllMocks();
  });

  it("archives, then hides, then toasts with an 8-second Undo; Undo unhides", async () => {
    const { result } = renderHook(() => useArchiveAndHide());
    await expect(result.current.archiveAndHide(args)).resolves.toBe(true);
    expect(calls).toEqual(["archive:p1", "hide:j1"]);
    expect(toast.success).toHaveBeenCalledWith(
      "Archived ExampleCo · TPM",
      expect.objectContaining({ duration: 8000, action: expect.objectContaining({ label: "Undo" }) }),
    );
    await toast.success.mock.calls[0]![1].action.onClick();
    expect(unhide).toHaveBeenCalledWith("j1");
  });

  it("returns false and shows an error toast when archiving fails", async () => {
    archive.mockRejectedValueOnce(new Error("boom"));
    const { result } = renderHook(() => useArchiveAndHide());
    await expect(result.current.archiveAndHide(args)).resolves.toBe(false);
    expect(hide).not.toHaveBeenCalled();
    expect(toast.error).toHaveBeenCalled();
  });
});
