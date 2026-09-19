import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { toast } from "sonner";
import { describe, expect, it, vi } from "vitest";
import { packageKeys, type Block } from "@/lib/api/queries";
import { BlocksTab } from "./BlocksTab";

const blockWithPeriod: Block = {
  id: "acme-migration",
  type: "achievement",
  org: "Acme Analytics",
  role: null,
  period: "2023",
  verified: true,
  metric: "18%",
  content: "Owned it.",
  tags: ["migration"],
  attribution: null,
  concurrent: false,
  visibility: null,
};

const blockNoPeriod: Block = {
  id: "globex-role",
  type: "role",
  org: "Globex",
  role: "Engineer",
  period: null,
  verified: false,
  metric: null,
  content: "Did the thing.",
  tags: [],
  attribution: null,
  concurrent: false,
  visibility: null,
};

// Mutable so each test can stage exactly the rows it needs — a fixed shared fixture across every
// test in the file is how a mock ends up returning the same thing regardless of what a test set up.
let blocksData: Block[] = [blockWithPeriod];

const putMutate = vi.fn().mockResolvedValue({});
const deleteMutate = vi.fn();
vi.mock("@/lib/api/queries", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/queries")>()),
  useBlocks: () => ({ data: blocksData, isLoading: false, error: null }),
  usePutBlock: () => ({ mutateAsync: putMutate, isPending: false }),
  useDeleteBlock: () => ({ mutateAsync: deleteMutate, isPending: false }),
}));

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

function renderTab() {
  // Seed the cache at the same key BlocksTab reads from (readBlock/patchBlock prefer the query
  // cache over the render-time `blocks.data` prop, precisely so a mutation can compose from the
  // freshest known copy of a block instead of a stale closure — see BlocksTab.tsx). Without this
  // seed, that cache-preferring read would silently fall through to the `blocks.data` fallback on
  // every read, and a test exercising the fresh-read behavior itself couldn't fail.
  const client = new QueryClient();
  client.setQueryData(packageKeys.blocks, blocksData);
  render(
    <QueryClientProvider client={client}>
      <BlocksTab />
    </QueryClientProvider>,
  );
  return client;
}

describe("BlocksTab", () => {
  it("lists blocks and opens the editor prefilled", async () => {
    blocksData = [blockWithPeriod];
    renderTab();
    expect(screen.getByText("acme-migration")).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: /edit acme-migration/i }));
    expect(screen.getByLabelText(/^content/i)).toHaveValue("Owned it.");
    expect(screen.getByLabelText(/^verified/i)).toBeChecked();
  });

  it("opens the editor as a centred dialog, not a sheet, with Save reachable", async () => {
    blocksData = [blockWithPeriod];
    renderTab();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /edit acme-migration/i }));

    const dialog = screen.getByRole("dialog");
    expect(dialog).toBeInTheDocument();
    expect(dialog.getAttribute("data-slot")).toBe("dialog-content");
    // A Sheet is built from the same underlying primitive but is identifiable by data-side, which
    // only SheetContent sets — this converted editor must not carry it.
    expect(dialog).not.toHaveAttribute("data-side");
    expect(screen.getByRole("button", { name: "Save" })).toBeVisible();
  });

  it("closes the confirm dialog and shows an error toast when delete fails", async () => {
    blocksData = [blockWithPeriod];
    deleteMutate.mockReset();
    deleteMutate.mockRejectedValueOnce(new Error("boom"));
    renderTab();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /delete acme-migration/i }));
    expect(screen.getByText(/delete acme-migration\?/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /^delete$/i }));
    expect(deleteMutate).toHaveBeenCalledWith("acme-migration");
    expect(toast.error).toHaveBeenCalled();
    expect(screen.queryByText(/delete acme-migration\?/i)).not.toBeInTheDocument();
  });

  it("toggles Verified with one click, PUTs the whole block with only that field flipped, and offers an Undo that reverts it", async () => {
    blocksData = [blockWithPeriod];
    putMutate.mockClear();
    renderTab();
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: /toggle verified for acme-migration/i }));

    expect(putMutate).toHaveBeenCalledTimes(1);
    expect(putMutate).toHaveBeenCalledWith({ ...blockWithPeriod, verified: false });

    expect(toast.success).toHaveBeenCalledWith(
      expect.stringMatching(/acme-migration/i),
      expect.objectContaining({ duration: 8000, action: expect.objectContaining({ label: "Undo" }) }),
    );

    const call = (toast.success as ReturnType<typeof vi.fn>).mock.calls[0]!;
    await call[1].action.onClick();
    expect(putMutate).toHaveBeenCalledTimes(2);
    expect(putMutate).toHaveBeenNthCalledWith(2, blockWithPeriod);
  });

  it("saves an inline Period edit on Enter", async () => {
    blocksData = [blockNoPeriod];
    putMutate.mockClear();
    renderTab();
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: /edit period for globex-role/i }));
    const input = screen.getByRole("textbox", { name: /period globex-role/i });
    await user.type(input, "2024{Enter}");

    expect(putMutate).toHaveBeenCalledWith({ ...blockNoPeriod, period: "2024" });
    expect(screen.queryByRole("textbox", { name: /period globex-role/i })).not.toBeInTheDocument();
  });

  it("cancels an inline Period edit on Escape without saving", async () => {
    blocksData = [blockNoPeriod];
    putMutate.mockClear();
    renderTab();
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: /edit period for globex-role/i }));
    const input = screen.getByRole("textbox", { name: /period globex-role/i });
    await user.type(input, "2024{Escape}");

    expect(putMutate).not.toHaveBeenCalled();
    expect(screen.queryByRole("textbox", { name: /period globex-role/i })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /edit period for globex-role/i })).toBeInTheDocument();
  });

  it("shows a chip counting blocks with no period and filters the table to just those", async () => {
    blocksData = [blockWithPeriod, blockNoPeriod];
    renderTab();
    const user = userEvent.setup();

    expect(screen.getByText("acme-migration")).toBeInTheDocument();
    expect(screen.getByText("globex-role")).toBeInTheDocument();

    const chip = screen.getByRole("button", { name: /1 needs a period/i });
    await user.click(chip);

    expect(screen.queryByText("acme-migration")).not.toBeInTheDocument();
    expect(screen.getByText("globex-role")).toBeInTheDocument();

    await user.click(chip);
    expect(screen.getByText("acme-migration")).toBeInTheDocument();
  });

  it("does not show the chip when every block has a period", () => {
    blocksData = [blockWithPeriod];
    renderTab();
    expect(screen.queryByText(/need.* a period/i)).not.toBeInTheDocument();
  });

  it("Undo after a Verified toggle only reverts verified — an interleaved Period edit survives — CRITICAL", async () => {
    // blockWithPeriod starts verified: true, period: "2023".
    blocksData = [blockWithPeriod];
    putMutate.mockClear();
    renderTab();
    const user = userEvent.setup();

    // Toggle verified off. Undo, if implemented as "re-PUT the pre-toggle snapshot", would capture
    // { ...blockWithPeriod, verified: true } here — including the *original* period.
    await user.click(screen.getByRole("button", { name: /toggle verified for acme-migration/i }));
    expect(putMutate).toHaveBeenLastCalledWith({ ...blockWithPeriod, verified: false });

    // While that Undo toast is still up, edit Period on the *same* block.
    await user.click(screen.getByRole("button", { name: /edit period for acme-migration/i }));
    const input = screen.getByRole("textbox", { name: /period acme-migration/i });
    await user.clear(input);
    await user.type(input, "2030{Enter}");
    expect(putMutate).toHaveBeenLastCalledWith({ ...blockWithPeriod, verified: false, period: "2030" });

    // Now Undo the toggle. Correct behaviour: only `verified` flips back to true; the period edit
    // made in between is untouched. The bug this guards against: Undo re-PUTting the stale
    // pre-toggle snapshot, which would silently revert period back to "2023".
    const toggleToast = (toast.success as ReturnType<typeof vi.fn>).mock.calls.find(
      ([, opts]) => opts?.action?.label === "Undo",
    )!;
    await toggleToast[1].action.onClick();

    expect(putMutate).toHaveBeenLastCalledWith({ ...blockWithPeriod, verified: true, period: "2030" });
  });
});
