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
    const source = within(region!);
    expect(source.getByText("verified: true")).toBeInTheDocument();
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

    bullet.focus();
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
    expect(screen.getByText("no-unverified-metrics")).toBeInTheDocument();
    expect(screen.getByText("sections[0].entries[1].bullets[2]")).toBeInTheDocument();
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
