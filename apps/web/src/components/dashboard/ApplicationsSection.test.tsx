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
});
