import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Board } from "./Board";
import type { ApplicationOut, BoardOut } from "@/lib/api/queries";
import type { DragEndEvent } from "@dnd-kit/core";

function app(id: string, status: string, history: { status: string; at: string }[] = [{ status, at: "2026-09-09T10:00:00Z" }]): ApplicationOut {
  return {
    id,
    job: { id: `job-${id}`, company: "ExampleCo", title: "PM" },
    package_id: null,
    status,
    applied_at: null,
    notes: "",
    status_history: history,
    created_at: "2026-09-09T10:00:00Z",
    updated_at: "2026-09-09T10:00:00Z",
  } as ApplicationOut;
}

function emptyColumns() {
  return { discovered: [], queued: [], applied: [], screen: [], interview: [], offer: [], closed: [] };
}

let boardData: BoardOut;
const refetch = vi.fn();
const mutateAsync = vi.fn();
const deleteMutateAsync = vi.fn();
let capturedOnDragEnd: ((event: DragEndEvent) => void | Promise<void>) | null = null;

vi.mock("@dnd-kit/core", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@dnd-kit/core")>();
  return {
    ...actual,
    useDraggable: () => ({ attributes: {}, listeners: {}, setNodeRef: () => undefined, transform: null, isDragging: false }),
    useDroppable: () => ({ setNodeRef: () => undefined, isOver: false }),
    DndContext: ({ children, onDragEnd }: { children: React.ReactNode; onDragEnd: (event: DragEndEvent) => void | Promise<void> }) => {
      capturedOnDragEnd = onDragEnd;
      return <>{children}</>;
    },
  };
});

vi.mock("@/lib/api/queries", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/queries")>()),
  useApplications: () => ({ data: boardData, error: null, refetch }),
  usePatchApplication: () => ({ mutateAsync, isPending: false }),
  useDeleteApplication: () => ({ mutateAsync: deleteMutateAsync, isPending: false }),
}));

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

describe("Board", () => {
  beforeEach(() => {
    refetch.mockReset();
    mutateAsync.mockReset();
    deleteMutateAsync.mockReset();
    capturedOnDragEnd = null;
    boardData = { columns: { ...emptyColumns(), queued: [app("a", "queued")] } } as unknown as BoardOut;
  });

  it("keeps the open sheet bound to live data instead of a stale snapshot", async () => {
    const user = userEvent.setup();
    const { rerender } = render(<Board />);

    await user.click(screen.getByRole("button", { name: /open/i }));
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getAllByRole("listitem")).toHaveLength(1);

    // Simulate a refetch (e.g. after a status change from the sheet, or from
    // elsewhere) landing new data for the same application without the sheet
    // being closed and reopened.
    boardData = {
      columns: {
        ...emptyColumns(),
        applied: [
          app("a", "applied", [
            { status: "queued", at: "2026-09-09T10:00:00Z" },
            { status: "applied", at: "2026-09-09T11:00:00Z" },
          ]),
        ],
      },
    } as unknown as BoardOut;
    rerender(<Board />);

    const dialogAfter = screen.getByRole("dialog");
    expect(within(dialogAfter).getAllByRole("listitem")).toHaveLength(2);
    expect(within(dialogAfter).getByText("Applied")).toBeInTheDocument();
  });

  it("closes the sheet when the open application disappears (e.g. after delete)", async () => {
    const user = userEvent.setup();
    const { rerender } = render(<Board />);
    await user.click(screen.getByRole("button", { name: /open/i }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();

    boardData = { columns: emptyColumns() } as unknown as BoardOut;
    rerender(<Board />);
    expect(screen.queryAllByRole("dialog")).toHaveLength(0);
  });

  it("refetches before clearing the optimistic override on a successful move", async () => {
    const order: string[] = [];
    mutateAsync.mockImplementation(async () => {
      order.push("mutate");
    });
    refetch.mockImplementation(async () => {
      order.push("refetch");
    });
    render(<Board />);
    expect(capturedOnDragEnd).not.toBeNull();

    await act(async () => {
      await capturedOnDragEnd!({ active: { id: "a" }, over: { id: "applied" } } as unknown as DragEndEvent);
    });

    expect(mutateAsync).toHaveBeenCalledWith({ id: "a", body: { status: "applied" } });
    expect(refetch).toHaveBeenCalledTimes(1);
    expect(order).toEqual(["mutate", "refetch"]);
  });

  it("reverts immediately and skips the refetch when the move fails", async () => {
    mutateAsync.mockRejectedValueOnce(new Error("boom"));
    render(<Board />);
    expect(capturedOnDragEnd).not.toBeNull();

    await act(async () => {
      await capturedOnDragEnd!({ active: { id: "a" }, over: { id: "applied" } } as unknown as DragEndEvent);
    });

    expect(refetch).not.toHaveBeenCalled();
    const { toast } = await import("sonner");
    expect(toast.error).toHaveBeenCalled();
  });
});
