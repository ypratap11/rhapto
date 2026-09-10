import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { toast } from "sonner";
import { describe, expect, it, vi } from "vitest";
import { BlocksTab } from "./BlocksTab";

const putMutate = vi.fn();
const deleteMutate = vi.fn();
vi.mock("@/lib/api/queries", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/queries")>()),
  useBlocks: () => ({
    data: [
      { id: "acme-migration", type: "achievement", org: "Acme Analytics", role: null, period: "2023", verified: true, metric: "18%", content: "Owned it.", tags: ["migration"], attribution: null, concurrent: false, visibility: null },
    ],
    isLoading: false,
    error: null,
  }),
  usePutBlock: () => ({ mutateAsync: putMutate, isPending: false }),
  useDeleteBlock: () => ({ mutateAsync: deleteMutate, isPending: false }),
}));

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

describe("BlocksTab", () => {
  it("lists blocks and opens the editor prefilled", async () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <BlocksTab />
      </QueryClientProvider>,
    );
    expect(screen.getByText("acme-migration")).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: /edit acme-migration/i }));
    expect(screen.getByLabelText(/^content/i)).toHaveValue("Owned it.");
    expect(screen.getByLabelText(/^verified/i)).toBeChecked();
  });

  it("closes the confirm dialog and shows an error toast when delete fails", async () => {
    deleteMutate.mockReset();
    deleteMutate.mockRejectedValueOnce(new Error("boom"));
    render(
      <QueryClientProvider client={new QueryClient()}>
        <BlocksTab />
      </QueryClientProvider>,
    );
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /delete acme-migration/i }));
    expect(screen.getByText(/delete acme-migration\?/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /^delete$/i }));
    expect(deleteMutate).toHaveBeenCalledWith("acme-migration");
    expect(toast.error).toHaveBeenCalled();
    expect(screen.queryByText(/delete acme-migration\?/i)).not.toBeInTheDocument();
  });
});
