import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { GuardrailReport } from "@/lib/api/queries";
import blocked from "./__fixtures__/blocked-report.json";
import passedBlocks from "./__fixtures__/passed-blocks-report.json";
import passedTune from "./__fixtures__/passed-tune-report.json";
import { GuardrailPanel } from "./GuardrailPanel";

type Fixture = { report: unknown; checks: Record<string, string>; remedies: Record<string, string> };

function panel(f: Fixture, extra: { nodelessHref?: string; onSelect?: (p: string) => void } = {}) {
  return (
    <GuardrailPanel
      report={f.report as GuardrailReport}
      checks={f.checks}
      remedies={f.remedies}
      onSelect={extra.onSelect ?? vi.fn()}
      nodelessHref={extra.nodelessHref}
    />
  );
}

/** Everything the panel shows with the Details disclosure taken out. */
function textOutsideDetails(container: HTMLElement): string {
  const clone = container.cloneNode(true) as HTMLElement;
  clone.querySelectorAll("details").forEach((d) => d.remove());
  return clone.textContent ?? "";
}

describe("GuardrailPanel, a passed report", () => {
  it("tune: one line per rule that ran, in order, straight from the API, and nothing about numbers or sources", () => {
    const { container } = render(panel(passedTune));
    expect(screen.getByRole("heading", { name: "Truth check" })).toBeInTheDocument();
    expect(screen.getByText("Passed")).toBeInTheDocument();
    const lines = within(screen.getByRole("list", { name: "What was checked" })).getAllByRole("listitem");
    expect(lines.map((l) => l.textContent)).toEqual(Object.values(passedTune.checks));
    expect(container.textContent).not.toContain("Every line comes from");
  });

  it("blocks mode: the source and number sentences are there", () => {
    render(panel(passedBlocks));
    const lines = within(screen.getByRole("list", { name: "What was checked" })).getAllByRole("listitem");
    expect(lines.map((l) => l.textContent)).toEqual(passedBlocks.report.rules_run.map((id) => (passedBlocks.checks as Record<string, string>)[id]));
    expect(screen.getByText(passedBlocks.checks.provenance)).toBeInTheDocument();
    expect(screen.getByText(passedBlocks.checks["no-unverified-metrics"])).toBeInTheDocument();
  });

  it("names a rule it has no sentence for instead of dropping it", () => {
    const f = { ...passedTune, report: { ...passedTune.report, rules_run: [...passedTune.report.rules_run, "some-future-rule"] } };
    render(panel(f));
    expect(screen.getByText("Checked: some future rule")).toBeInTheDocument();
  });

  it("lists a warning as 'Heads up' even though the report passed", () => {
    render(panel(passedBlocks));
    expect(screen.getByText("Passed")).toBeInTheDocument();
    expect(screen.getByText("Heads up")).toBeInTheDocument();
    expect(screen.getByText(passedBlocks.remedies.completeness)).toBeInTheDocument();
  });
});

describe("GuardrailPanel, a report that did not pass", () => {
  it("says it was held back, and shows the remedy as the visible line", () => {
    const { container } = render(panel(blocked));
    expect(screen.getByText("Needs attention")).toBeInTheDocument();
    expect(screen.getByText("Rhapto held this resume back because some lines did not pass the truth check.")).toBeInTheDocument();
    expect(screen.getByText(blocked.remedies["no-unverified-metrics"])).toBeInTheDocument();
    // The engine's own message is for Details only.
    expect(textOutsideDetails(container)).not.toContain(blocked.report.violations[0].message);
  });

  it("falls back to the message when there is no remedy for the rule", () => {
    const f = { ...blocked, remedies: {} };
    const { container } = render(panel(f));
    expect(textOutsideDetails(container)).toContain(blocked.report.violations[0].message);
  });

  it("gives an error on a node a Fix button that selects its path", async () => {
    const onSelect = vi.fn();
    render(panel(blocked, { onSelect }));
    await userEvent.setup().click(screen.getByRole("button", { name: /^Fix/ }));
    expect(onSelect).toHaveBeenCalledWith("sections[0].entries[0].bullets[1]");
  });

  it("gives a node-less violation a Fix link only when it is given somewhere to go", () => {
    const { unmount } = render(panel(blocked));
    expect(screen.queryByRole("link", { name: /^Fix/ })).not.toBeInTheDocument();
    unmount();
    render(panel(blocked, { nodelessHref: "/jobs/j1/packages/p1" }));
    expect(screen.getByRole("link", { name: /^Fix/ })).toHaveAttribute("href", "/jobs/j1/packages/p1");
    expect(screen.queryAllByRole("button", { name: /^Fix/ })).toHaveLength(1);
  });

  it("shows a warning as 'Heads up', not as the reason it was held back", () => {
    render(panel(blocked));
    const heads = screen.getByText("Heads up").closest("div")!;
    expect(within(heads).getByText(blocked.remedies.completeness)).toBeInTheDocument();
  });
});

describe("GuardrailPanel, Details", () => {
  it("is closed, has a tall summary, and holds the ids, severities, block and path", () => {
    const { container } = render(panel(blocked));
    const details = container.querySelector("details") as HTMLDetailsElement;
    expect(details.open).toBe(false);
    const summary = details.querySelector("summary")!;
    expect(summary).toHaveTextContent("Details");
    expect(summary.className).toContain("min-h-11");
    const inside = within(details);
    expect(inside.getAllByText("no-unverified-metrics").length).toBeGreaterThan(0);
    expect(inside.getByText("sections[0].entries[0].bullets[1]")).toBeInTheDocument();
    expect(inside.getByText("acme-migration")).toBeInTheDocument();
    expect(inside.getByText("error")).toBeInTheDocument();
    expect(inside.getByText(blocked.report.violations[0].message)).toBeInTheDocument();
    const outside = textOutsideDetails(container);
    for (const needle of ["no-unverified-metrics", "sections[0]", "acme-migration", "selection.block_ids"]) {
      expect(outside).not.toContain(needle);
    }
  });

  it("keeps jargon out of everything visible, on every real report", () => {
    for (const f of [blocked, passedBlocks, passedTune]) {
      const { container, unmount } = render(panel(f, { nodelessHref: "/jobs/j1/packages/p1" }));
      const outside = textOutsideDetails(container).toLowerCase();
      for (const word of ["block", "verified", "library", "guardrail", "provenance"]) {
        expect(outside, `"${word}" visible`).not.toContain(word);
      }
      expect(outside).not.toContain("rules run");
      unmount();
    }
  });
});
