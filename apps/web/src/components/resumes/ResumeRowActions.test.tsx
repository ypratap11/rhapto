import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { PackageListItem } from "@/lib/api/queries";
import { ResumeRowActions } from "./ResumeRowActions";

const markReady = vi.fn().mockResolvedValue({});
const archive = vi.fn().mockResolvedValue({});
const hide = vi.fn().mockResolvedValue({});
const unhide = vi.fn().mockResolvedValue({});
vi.mock("@/lib/api/queries", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/queries")>()),
  useMarkPackageReady: () => ({ mutateAsync: markReady, isPending: false }),
  useArchivePackage: () => ({ mutateAsync: archive, isPending: false }),
  useHideJob: () => ({ mutateAsync: hide, isPending: false }),
  useUnhideJob: () => ({ mutateAsync: unhide, isPending: false }),
}));
// `vi.mock`'s factory runs the moment "./ResumeRowActions" is loaded — before this file's own
// top-level `const`s have executed — so referencing an outer `toast` directly here would hit its
// temporal dead zone. `vi.hoisted` runs first and sidesteps that (see NotInterestedButton.test.tsx).
const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast }));

const row = { id: "p1", job_id: "j1", company: "ExampleCo", title: "TPM", status: "draft", version: 2 } as PackageListItem;

describe("ResumeRowActions", () => {
  it("links Review at the review page", () => {
    render(<ResumeRowActions row={row} />);
    expect(screen.getByRole("link", { name: /review/i })).toHaveAttribute("href", "/jobs/j1/packages/p1");
  });

  it("marks a draft ready", async () => {
    const user = userEvent.setup({ delay: null });
    render(<ResumeRowActions row={row} />);
    await user.click(screen.getByRole("button", { name: /mark ready/i }));
    expect(markReady).toHaveBeenCalledWith("p1");
  });

  it("Skip archives the package, hides the job, and offers Undo for 8 seconds", async () => {
    const user = userEvent.setup({ delay: null });
    render(<ResumeRowActions row={row} />);
    await user.click(screen.getByRole("button", { name: /^skip$/i }));
    expect(archive).toHaveBeenCalledWith("p1");
    expect(hide).toHaveBeenCalledWith("j1");
    expect(toast.success).toHaveBeenCalledWith(expect.stringContaining("Skipped"), expect.objectContaining({ duration: 8000 }));
  });
});
