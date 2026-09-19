import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { BasesTab } from "./BasesTab";

const putMutate = vi.fn().mockResolvedValue({});
const deleteMutate = vi.fn().mockResolvedValue({});
vi.mock("@/lib/api/queries", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/queries")>()),
  useBases: () => ({
    data: [{ id: "default", name: "Default", block_ids: [], section_order: ["summary"], style: {} }],
    isLoading: false,
    error: null,
  }),
  useBlocks: () => ({ data: [], isLoading: false, error: null }),
  usePutBase: () => ({ mutateAsync: putMutate, isPending: false }),
  useDeleteBase: () => ({ mutateAsync: deleteMutate, isPending: false }),
}));

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

describe("BasesTab", () => {
  it("opens the base editor as a centred dialog, not a sheet, with Save reachable", async () => {
    render(<BasesTab />);
    const user = userEvent.setup({ delay: null });
    await user.click(screen.getByRole("button", { name: /edit default/i }));

    const dialog = screen.getByRole("dialog");
    expect(dialog).toBeInTheDocument();
    expect(dialog.getAttribute("data-slot")).toBe("dialog-content");
    expect(dialog).not.toHaveAttribute("data-side");
    expect(screen.getByRole("button", { name: "Save" })).toBeVisible();
  });
});
