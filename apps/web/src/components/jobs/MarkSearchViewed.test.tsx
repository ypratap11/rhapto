import { render } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MarkSearchViewed } from "./MarkSearchViewed";

const mutateAsync = vi.fn().mockResolvedValue({});
vi.mock("@/lib/api/queries", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/queries")>()),
  useMarkSearchViewed: () => ({ mutateAsync, isPending: false }),
}));
// Same TDZ hazard as NotInterestedButton.test.tsx: the "sonner" mock factory reads `toast`
// directly, and runs (via "./MarkSearchViewed"'s own `import "sonner"`) before this file's own
// top-level `const`s would otherwise have run.
const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast }));

describe("MarkSearchViewed", () => {
  beforeEach(() => {
    mutateAsync.mockReset().mockResolvedValue({});
    toast.error.mockReset();
    toast.success.mockReset();
  });

  it("marks the given search viewed once and stays quiet on success", async () => {
    render(<MarkSearchViewed searchId="s1" />);
    await vi.waitFor(() => expect(mutateAsync).toHaveBeenCalledWith("s1"));
    expect(mutateAsync).toHaveBeenCalledTimes(1);
    expect(toast.error).not.toHaveBeenCalled();
  });

  it("toasts when marking the search as viewed fails, instead of leaving a stuck badge silent", async () => {
    mutateAsync.mockRejectedValueOnce(new Error("boom"));
    render(<MarkSearchViewed searchId="s2" />);
    await vi.waitFor(() => expect(toast.error).toHaveBeenCalledWith("Could not mark this search as viewed"));
  });

  it("marks a new id again when the id changes", async () => {
    const { rerender } = render(<MarkSearchViewed searchId="s3" />);
    await vi.waitFor(() => expect(mutateAsync).toHaveBeenCalledWith("s3"));

    rerender(<MarkSearchViewed searchId="s4" />);
    await vi.waitFor(() => expect(mutateAsync).toHaveBeenCalledWith("s4"));
  });
});
