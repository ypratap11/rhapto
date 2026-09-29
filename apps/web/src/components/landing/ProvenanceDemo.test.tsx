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
    // A verified bullet shows its own block id, so the reader can reconcile it with the block ids
    // the hero's caught cases cite. This is also product rule 2 made visible.
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

  it("no longer carries the invent toggle, the invented bullet, or the false 'blocked before produced' claim", () => {
    // The catch moved to CaughtDemo in the hero. What stayed is only "click a line to see its
    // source"; a blocked package is not claimed to produce no document anywhere in this demo.
    const { container } = render(<ProvenanceDemo />);
    expect(screen.queryByRole("switch")).toBeNull();
    const text = container.textContent ?? "";
    expect(text).not.toMatch(/increased forecast accuracy|no-unverified-metrics|acme-forecast/i);
    expect(text).not.toMatch(/blocked before this document was produced/i);
  });
});
