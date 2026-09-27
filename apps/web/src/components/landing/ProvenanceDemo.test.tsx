import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { ProvenanceDemo } from "./ProvenanceDemo";

describe("ProvenanceDemo", () => {
  it("keeps each bullet's source collapsed until it is activated, with real buttons and aria-expanded", () => {
    render(<ProvenanceDemo />);
    const bullets = screen.getAllByRole("button", { name: /cutting|migrated/i });
    expect(bullets).toHaveLength(2);
    for (const bullet of bullets) expect(bullet).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText("verified: true")).not.toBeInTheDocument();
  });

  it("reveals org, role, period and the exact sentence on click, styled as provenance, and collapses again", async () => {
    render(<ProvenanceDemo />);
    const user = userEvent.setup();
    const bullet = screen.getByRole("button", { name: /migrated 12 pipelines/i });

    await user.click(bullet);
    expect(bullet).toHaveAttribute("aria-expanded", "true");
    const region = document.getElementById(bullet.getAttribute("aria-controls")!);
    expect(region).not.toBeNull();
    // "styled as provenance" is half the claim: this panel means "this came from somewhere", and
    // the token that says so is the one the app already uses for it. Without this line, swapping it
    // for the deleted-red panel would leave every other assertion here passing.
    expect(region).toHaveClass("bg-diff-add-bg");
    const source = within(region!);
    expect(source.getByText("verified: true")).toBeInTheDocument();
    // The refusal below names a block id, so a verified bullet has to show its own for the reader to
    // have anything to reconcile it against. This is also product rule 2 made visible.
    expect(source.getByText("block: acme-migration")).toBeInTheDocument();
    expect(source.getByText(/Acme Analytics/)).toBeInTheDocument();
    expect(source.getByText(/Senior Data Program Manager/)).toBeInTheDocument();
    expect(source.getByText(/2019.2023/)).toBeInTheDocument();
    expect(
      source.getByText(/“Migrated 12 pipelines to Snowflake with zero downtime, cutting warehouse cost 18%\.”/),
    ).toBeInTheDocument();

    await user.click(bullet);
    expect(bullet).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText("verified: true")).not.toBeInTheDocument();
  });

  it("is keyboard-operable: Tab then Enter reveals the source, without clicking anything", async () => {
    render(<ProvenanceDemo />);
    const user = userEvent.setup();
    const bullet = screen.getByRole("button", { name: /redesigned the customer onboarding/i });

    // Really press Tab rather than calling .focus(): the bullets are the first things in the demo
    // a keyboard user reaches, and .focus() would pass even on an element Tab can never land on.
    await user.tab();
    expect(bullet).toHaveFocus();
    await user.keyboard("{Enter}");

    expect(bullet).toHaveAttribute("aria-expanded", "true");
    const region = document.getElementById(bullet.getAttribute("aria-controls")!);
    expect(within(region!).getByText(/Northwind Labs/)).toBeInTheDocument();
  });

  it("hides the invented bullet and its guardrail refusal until the toggle is switched on", () => {
    render(<ProvenanceDemo />);
    const toggle = screen.getByRole("switch", { name: /what happens when it invents something/i });
    expect(toggle).toHaveAttribute("aria-checked", "false");
    expect(screen.queryByText(/no-unverified-metrics/)).not.toBeInTheDocument();
    expect(screen.queryByText(/increased forecast accuracy by 42%/i)).not.toBeInTheDocument();
  });

  it("shows the real guardrail shape -- rule, path and message -- once the toggle is switched on, and hides it again off", async () => {
    render(<ProvenanceDemo />);
    const user = userEvent.setup();
    const toggle = screen.getByRole("switch", { name: /what happens when it invents something/i });

    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-checked", "true");
    expect(screen.getByText(/increased forecast accuracy by 42%/i)).toBeInTheDocument();
    // `line-through` is CSS; the accessibility tree never sees it, and role="status" announces this
    // region atomically in DOM order -- fabricated sentence first. Without this text a screen reader
    // states the unverified metric as plain prose before saying it was blocked.
    expect(screen.getByText(/Rejected draft bullet:/)).toBeInTheDocument();
    expect(screen.getByText("no-unverified-metrics")).toBeInTheDocument();
    expect(screen.getByText("sections[0].entries[1].bullets[1]")).toBeInTheDocument();
    expect(
      screen.getByText(/block 'acme-forecast' is not verified but the text contains metric\(s\): 42%/),
    ).toBeInTheDocument();

    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-checked", "false");
    expect(screen.queryByText(/increased forecast accuracy by 42%/i)).not.toBeInTheDocument();
  });

  it("also toggles the invented bullet when its own visible label is clicked, not only the switch", async () => {
    render(<ProvenanceDemo />);
    const user = userEvent.setup();
    await user.click(screen.getByText("What happens when it invents something"));
    expect(screen.getByRole("switch", { name: /what happens when it invents something/i })).toHaveAttribute(
      "aria-checked",
      "true",
    );
  });
});
