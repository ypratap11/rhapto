import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ApplicationOut } from "@/lib/api/queries";
import type { ChipId } from "@/lib/applications-view";
import { ApplicationsSection } from "./ApplicationsSection";

// The filter and the open application are the page's now (the hero tiles and the next-step card drive them),
// so this section is exercised through a small controlled harness. The chip row it used to own is gone:
// the tiles replaced it, and their behaviour is tested in the page test.
const NOW = new Date("2026-10-11T12:00:00Z");
beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(NOW);
});
afterEach(() => vi.useRealTimers());

const row = (id: string, status: string, updated_at: string, closed_reason: string | null = null, extra: Partial<ApplicationOut> = {}) =>
  ({
    id,
    status,
    updated_at,
    closed_reason,
    notes: "",
    follow_up_at: null,
    applied_at: null,
    package_id: null,
    status_history: [],
    job: { id: `j${id}`, company: `Co ${id}`, title: "TPM" },
    ...extra,
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

function Harness({ rows, dueIds, initial = "all", onSelect = () => {} }: { rows: ApplicationOut[]; dueIds?: ReadonlySet<string>; initial?: ChipId; onSelect?: (id: string) => void }) {
  const [chip, setChip] = useState<ChipId>(initial);
  return <ApplicationsSection rows={rows} dueIds={dueIds} chip={chip} onChipChange={setChip} onSelect={onSelect} />;
}

describe("ApplicationsSection", () => {
  it("is the Your applications region", () => {
    render(<Harness rows={seven} />);
    expect(screen.getByRole("region", { name: "Your applications" })).toBeInTheDocument();
  });

  it("filters to the chosen status and says so, with a way back", async () => {
    const user = userEvent.setup({ delay: null });
    render(<Harness rows={all} initial="interviewing" />);
    expect(screen.getByText("Co 3")).toBeInTheDocument();
    expect(screen.queryByText("Co 4")).toBeNull();
    expect(screen.getByText(/Showing:/)).toHaveTextContent("Showing: Interviewing");
    await user.click(screen.getByRole("button", { name: "Show all applications" }));
    expect(screen.getByText("Co 4")).toBeInTheDocument();
    expect(screen.queryByText(/Showing:/)).toBeNull();
  });

  it("shows no filter line when nothing is filtered", () => {
    render(<Harness rows={all} />);
    expect(screen.queryByText(/Showing:/)).toBeNull();
  });

  it("says statuses in words", () => {
    render(<Harness rows={seven} />);
    expect(screen.getByText("Rejected")).toBeInTheDocument();
    expect(screen.getByText("Position filled")).toBeInTheDocument();
    expect(screen.getByText("Screening")).toBeInTheDocument();
  });

  it("says when you applied and how long ago, else when it last changed", () => {
    render(
      <Harness
        rows={[
          row("1", "applied", "2026-10-10T00:00:00Z", null, { applied_at: "2026-09-29T00:00:00Z" }),
          row("2", "interview", "2026-10-10T00:00:00Z", null, { status_history: [{ at: "2026-10-09T00:00:00Z" }] as never }),
        ]}
      />,
    );
    expect(screen.getByText("Applied 29 Sep 2026 · 12 days ago")).toBeInTheDocument();
    expect(screen.getByText("Updated 9 Oct 2026 · 2 days ago")).toBeInTheDocument();
  });

  it("shows six rows and reveals the rest", async () => {
    const user = userEvent.setup({ delay: null });
    render(<Harness rows={all} />);
    const list = () => within(screen.getByRole("region", { name: "Your applications" })).getAllByRole("listitem");
    expect(list()).toHaveLength(6);
    await user.click(screen.getByRole("button", { name: "Show all 15" }));
    expect(list()).toHaveLength(15);
    expect(screen.queryByRole("button", { name: /^Show all \d+/ })).toBeNull();
  });

  it("folds the list again when the filter changes", async () => {
    const user = userEvent.setup({ delay: null });
    render(<Harness rows={all} initial="applied" />);
    await user.click(screen.getByRole("button", { name: "Show all 10" }));
    await user.click(screen.getByRole("button", { name: "Show all applications" }));
    expect(screen.getByRole("button", { name: "Show all 15" })).toBeInTheDocument();
  });

  it("hands the clicked application to the page", async () => {
    const user = userEvent.setup({ delay: null });
    const onSelect = vi.fn();
    render(<Harness rows={seven} onSelect={onSelect} />);
    await user.click(screen.getByText("Co 3"));
    expect(onSelect).toHaveBeenCalledWith("3");
  });

  describe("bar", () => {
    it("is one image with the counts as its label", () => {
      render(<Harness rows={all} />);
      expect(screen.getByRole("img", { name: "10 applied, 1 interviewing, 1 offer, 3 closed" })).toBeInTheDocument();
    });

    it("sizes segments in proportion to the counts", () => {
      render(<Harness rows={all} />);
      const bar = screen.getByRole("img", { name: /applied/ });
      const widths = Array.from(bar.children).map((c) => (c as HTMLElement).style.width);
      expect(widths).toEqual(["66.66666666666666%", "6.666666666666667%", "6.666666666666667%", "20%"]);
    });

    it("lists the four counts in the legend", () => {
      render(<Harness rows={all} />);
      for (const text of ["Applied 10", "Interviewing 1", "Offer 1", "Closed 3"]) expect(screen.getByText(text)).toBeInTheDocument();
    });
  });

  describe("follow-ups due", () => {
    const due = new Set(["2", "x1"]);

    it("badges only the rows whose follow-up is due", () => {
      render(<Harness rows={all} dueIds={due} initial="all" />);
      expect(screen.queryAllByText("Follow up")).toHaveLength(1); // x1 is beyond the first six rows
      expect(within(screen.getByText("Follow up").closest("li")!).getByText("Co 2")).toBeInTheDocument();
    });

    it("shows no badge when nothing is due", () => {
      render(<Harness rows={all} dueIds={new Set()} />);
      expect(screen.queryByText("Follow up")).toBeNull();
    });

    it("ignores due ids that match no row", () => {
      render(<Harness rows={seven} dueIds={new Set(["gone"])} />);
      expect(screen.queryByText("Follow up")).toBeNull();
    });
  });

  describe("tip", () => {
    const sent = (id: string, daysAgo: number, extra: Partial<ApplicationOut> = {}) =>
      row(id, "applied", "2026-10-10T00:00:00Z", null, { applied_at: new Date(NOW.getTime() - daysAgo * 86_400_000).toISOString(), ...extra });

    it("asks about an application sent seven days ago and opens its sheet", async () => {
      const user = userEvent.setup({ delay: null });
      const onSelect = vi.fn();
      render(<Harness rows={[sent("a", 7)]} onSelect={onSelect} />);
      expect(screen.getByText("Heard back from Co a?")).toBeInTheDocument();
      expect(screen.getByText("Mark the reply so your dashboard stays current.")).toBeInTheDocument();
      await user.click(screen.getByRole("button", { name: "Update status →" }));
      expect(onSelect).toHaveBeenCalledWith("a");
    });

    it("stays away at six days, and when a follow-up date is set", () => {
      render(<Harness rows={[sent("a", 6), sent("b", 30, { follow_up_at: "2026-10-20T00:00:00Z" })]} />);
      expect(screen.queryByText(/Heard back from/)).toBeNull();
    });
  });

  it("says so when the filter matches nothing", () => {
    render(<Harness rows={extra} initial="offer" />);
    expect(screen.getByText("Nothing here yet.")).toBeInTheDocument();
  });
});
