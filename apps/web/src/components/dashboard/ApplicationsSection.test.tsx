import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { ApplicationOut } from "@/lib/api/queries";
import { ApplicationsSection } from "./ApplicationsSection";

vi.mock("@/lib/api/queries", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/queries")>()),
  usePatchApplication: () => ({ mutateAsync: vi.fn().mockResolvedValue({}), isPending: false }),
  useDeleteApplication: () => ({ mutateAsync: vi.fn().mockResolvedValue({}), isPending: false }),
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const row = (id: string, status: string, updated_at: string, closed_reason: string | null = null) =>
  ({
    id,
    status,
    updated_at,
    closed_reason,
    notes: "",
    follow_up_at: null,
    package_id: null,
    status_history: [],
    job: { id: `j${id}`, company: `Co ${id}`, title: "TPM" },
  }) as unknown as ApplicationOut;

const seven = [
  row("1", "applied", "2026-10-01T00:00:00Z"),
  row("2", "screen", "2026-10-02T00:00:00Z"),
  row("3", "interview", "2026-10-03T00:00:00Z"),
  row("4", "offer", "2026-10-04T00:00:00Z"),
  row("5", "closed", "2026-10-05T00:00:00Z", "rejected"),
  row("6", "closed", "2026-10-06T00:00:00Z", "filled"),
  row("7", "closed", "2026-10-07T00:00:00Z"),
];
const extra = Array.from({ length: 8 }, (_, i) => row(`x${i}`, "applied", `2026-09-0${i + 1}T00:00:00Z`));
const all = [...seven, ...extra];

const chipNames = () =>
  within(screen.getByRole("group", { name: "Filter applications" }))
    .getAllByRole("button")
    .map((b) => b.textContent);

describe("ApplicationsSection chip row", () => {
  it("is one non-wrapping, horizontally scrollable row with a hidden scrollbar", () => {
    render(<ApplicationsSection rows={all} dueIds={new Set(["2"])} />);
    const group = screen.getByRole("group", { name: "Filter applications" });
    expect(group.className).toMatch(/flex-nowrap/);
    expect(group.className).toMatch(/overflow-x-auto/);
    expect(group.className).toMatch(/scrollbar-width:none/);
    for (const b of within(group).getAllByRole("button")) expect(b.className).toMatch(/shrink-0/);
  });

  it("brings the active chip into view with the row's scrollLeft, never scrollIntoView", async () => {
    const intoView = vi.fn();
    Element.prototype.scrollIntoView = intoView;
    const offsetLeft = vi.spyOn(HTMLElement.prototype, "offsetLeft", "get").mockReturnValue(300);
    const offsetWidth = vi.spyOn(HTMLElement.prototype, "offsetWidth", "get").mockReturnValue(40);
    const clientWidth = vi.spyOn(HTMLElement.prototype, "clientWidth", "get").mockReturnValue(100);
    try {
      const user = userEvent.setup({ delay: null });
      render(<ApplicationsSection rows={all} />);
      const group = screen.getByRole("group", { name: "Filter applications" });
      await user.click(within(group).getByRole("button", { name: /^Closed/ }));
      expect(group.scrollLeft).toBe(270);
      expect(intoView).not.toHaveBeenCalled();
    } finally {
      offsetLeft.mockRestore();
      offsetWidth.mockRestore();
      clientWidth.mockRestore();
    }
  });
});

describe("ApplicationsSection initial scroll", () => {
  it("starts at scrollLeft 0 on load, even though a chip is active", () => {
    const offsetLeft = vi.spyOn(HTMLElement.prototype, "offsetLeft", "get").mockReturnValue(300);
    const offsetWidth = vi.spyOn(HTMLElement.prototype, "offsetWidth", "get").mockReturnValue(40);
    const clientWidth = vi.spyOn(HTMLElement.prototype, "clientWidth", "get").mockReturnValue(100);
    try {
      render(<ApplicationsSection rows={all} />);
      expect(screen.getByRole("group", { name: "Filter applications" }).scrollLeft).toBe(0);
    } finally {
      offsetLeft.mockRestore();
      offsetWidth.mockRestore();
      clientWidth.mockRestore();
    }
  });
});

describe("ApplicationsSection", () => {
  it("lists the chips in order with counts", () => {
    render(<ApplicationsSection rows={all} />);
    expect(chipNames()).toEqual(["Applied10", "Interviewing1", "Offer1", "Closed3", "All15"]);
  });

  it("still shows a chip with zero", () => {
    render(<ApplicationsSection rows={extra} />);
    expect(chipNames()).toContain("Offer0");
  });

  it("filters by chip", async () => {
    const user = userEvent.setup({ delay: null });
    render(<ApplicationsSection rows={all} />);
    await user.click(screen.getByRole("button", { name: /^Interviewing/ }));
    expect(screen.getByText("Co 3")).toBeInTheDocument();
    expect(screen.queryByText("Co 4")).toBeNull();
  });

  it("says statuses in words", () => {
    render(<ApplicationsSection rows={seven} />);
    expect(screen.getByText("Rejected")).toBeInTheDocument();
    expect(screen.getByText("Position filled")).toBeInTheDocument();
    expect(screen.getByText("Screening")).toBeInTheDocument();
  });

  it("shows the date of the last change on every row", () => {
    render(<ApplicationsSection rows={[row("1", "applied", "2026-09-29T00:00:00Z")]} />);
    expect(screen.getByText("29 Sep 2026")).toBeInTheDocument();
  });

  it("shows ten rows and reveals the rest", async () => {
    const user = userEvent.setup({ delay: null });
    render(<ApplicationsSection rows={all} />);
    expect(within(screen.getByRole("list")).getAllByRole("listitem")).toHaveLength(10);
    await user.click(screen.getByRole("button", { name: "Show all 15" }));
    expect(within(screen.getByRole("list")).getAllByRole("listitem")).toHaveLength(15);
  });

  it("opens the application sheet from a row", async () => {
    const user = userEvent.setup({ delay: null });
    render(<ApplicationsSection rows={seven} />);
    await user.click(screen.getByText("Co 3"));
    const dialog = await screen.findByRole("dialog", { name: "Co 3" });
    expect(within(dialog).getByRole("combobox", { name: "Status" })).toBeInTheDocument();
  });

  describe("follow-ups due", () => {
    const due = new Set(["2", "x1"]);

    it("badges only the rows whose follow-up is due", () => {
      render(<ApplicationsSection rows={all} dueIds={due} />);
      const items = within(screen.getByRole("list")).getAllByRole("listitem");
      const badged = items.filter((li) => within(li).queryByText("Follow up"));
      expect(badged).toHaveLength(1);
      expect(within(badged[0]!).getByText("Co 2")).toBeInTheDocument();
    });

    it("says how many are due and filters to them on click", async () => {
      const user = userEvent.setup({ delay: null });
      render(<ApplicationsSection rows={all} dueIds={due} />);
      await user.click(screen.getByRole("button", { name: "2 follow-ups due" }));
      const items = within(screen.getByRole("list")).getAllByRole("listitem");
      expect(items.map((li) => li.textContent)).toEqual([expect.stringContaining("Co 2"), expect.stringContaining("Co x1")]);
    });

    it("uses the singular for one", () => {
      render(<ApplicationsSection rows={all} dueIds={new Set(["3"])} />);
      expect(screen.getByRole("button", { name: "1 follow-up due" })).toBeInTheDocument();
    });

    it("sits last in the chip row, shows as a pressed chip, and un-presses the status chips", async () => {
      const user = userEvent.setup({ delay: null });
      render(<ApplicationsSection rows={all} dueIds={due} />);
      const group = screen.getByRole("group", { name: "Filter applications" });
      const buttons = within(group).getAllByRole("button");
      const toggle = buttons[buttons.length - 1]!;
      expect(toggle).toHaveTextContent("2 follow-ups due");
      expect(toggle.className).not.toMatch(/underline/);
      expect(within(group).getByRole("button", { name: /^All/ })).toHaveAttribute("aria-pressed", "true");
      await user.click(toggle);
      expect(toggle).toHaveAttribute("aria-pressed", "true");
      expect(toggle.className).toMatch(/border-primary/);
      expect(toggle.className).toMatch(/bg-primary\/10/);
      expect(within(group).getByRole("button", { name: /^All/ })).toHaveAttribute("aria-pressed", "false");
      expect(within(group).getByRole("button", { name: /^All/ }).className).not.toMatch(/border-primary/);
    });

    it("is hidden when nothing is due", () => {
      render(<ApplicationsSection rows={all} dueIds={new Set()} />);
      expect(screen.queryByText(/follow-ups? due/)).toBeNull();
      expect(screen.queryByText("Follow up")).toBeNull();
    });

    it("ignores due ids that match no row", () => {
      render(<ApplicationsSection rows={seven} dueIds={new Set(["gone"])} />);
      expect(screen.queryByText(/follow-ups? due/)).toBeNull();
    });
  });
});
