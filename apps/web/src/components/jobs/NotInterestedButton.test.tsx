import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { JobOut } from "@/lib/api/queries";
import { NotInterestedButton } from "./NotInterestedButton";

const hide = vi.fn().mockResolvedValue({});
const unhide = vi.fn().mockResolvedValue({});
vi.mock("@/lib/api/queries", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/queries")>()),
  useHideJob: () => ({ mutateAsync: hide, isPending: false }),
  useUnhideJob: () => ({ mutateAsync: unhide, isPending: false }),
}));
// `vi.mock`'s factory runs the moment "./NotInterestedButton" is loaded — before this file's own
// top-level `const`s have executed — so referencing an outer `toast` directly here would hit its
// temporal dead zone. `vi.hoisted` runs first and sidesteps that.
const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast }));

const job = { id: "j1", company: "ExampleCo", title: "TPM" } as JobOut;

describe("NotInterestedButton", () => {
  it("hides the job and offers Undo for 8 seconds", async () => {
    const user = userEvent.setup({ delay: null });
    render(<NotInterestedButton job={job} />);
    await user.click(screen.getByRole("button", { name: /not interested/i }));

    expect(hide).toHaveBeenCalledWith("j1");
    expect(toast.success).toHaveBeenCalledWith(
      "Hidden ExampleCo · TPM",
      expect.objectContaining({ duration: 8000, action: expect.objectContaining({ label: "Undo" }) }),
    );

    await toast.success.mock.calls[0]![1].action.onClick();
    expect(unhide).toHaveBeenCalledWith("j1");
  });
});
