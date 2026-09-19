import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { TracksTab } from "./TracksTab";

const putMutate = vi.fn().mockResolvedValue({});
const deleteMutate = vi.fn().mockResolvedValue({});
vi.mock("@/lib/api/queries", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/queries")>()),
  useTracks: () => ({
    data: [{ id: "backend-track", name: "Backend", description: "", keywords: [], resume_base: "default", min_fit: 50 }],
    isLoading: false,
    error: null,
  }),
  useBases: () => ({ data: [{ id: "default", name: "Default" }], isLoading: false, error: null }),
  usePutTrack: () => ({ mutateAsync: putMutate, isPending: false }),
  useDeleteTrack: () => ({ mutateAsync: deleteMutate, isPending: false }),
  useTaxonomy: () => ({ data: { fields: [] }, isLoading: false, error: null, isPaused: false }),
  useTaxonomySuggestions: () => ({ data: [], isLoading: false, error: null, isPaused: false }),
}));

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

describe("TracksTab", () => {
  it("opens the track editor as a centred dialog, not a sheet, with Save reachable", async () => {
    render(<TracksTab />);
    const user = userEvent.setup({ delay: null });
    await user.click(screen.getByRole("button", { name: /edit backend-track/i }));

    const dialog = screen.getByRole("dialog");
    expect(dialog).toBeInTheDocument();
    expect(dialog.getAttribute("data-slot")).toBe("dialog-content");
    // A Sheet is built from the same underlying primitive but is identifiable by data-side, which
    // only SheetContent sets — this converted editor must not carry it.
    expect(dialog).not.toHaveAttribute("data-side");
    expect(screen.getByRole("button", { name: "Save" })).toBeVisible();
  });
});
