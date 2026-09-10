import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { GuardrailPanel } from "./GuardrailPanel";

describe("GuardrailPanel", () => {
  it("shows passed state", () => {
    render(<GuardrailPanel report={{ passed: true, rules_run: ["provenance", "no-unverified-metrics"], violations: [] }} onSelect={vi.fn()} />);
    expect(screen.getByText(/all guardrails passed/i)).toBeInTheDocument();
    expect(screen.getByText("no-unverified-metrics")).toBeInTheDocument();
  });
  it("lists violations and selects their path on click", async () => {
    const onSelect = vi.fn();
    render(
      <GuardrailPanel
        report={{
          passed: false,
          rules_run: ["provenance"],
          violations: [{ rule: "no-unverified-metrics", severity: "error", message: "metric(s) not found: 25%", path: "sections[0].entries[0].bullets[1]", block_id: "acme-migration" }],
        }}
        onSelect={onSelect}
      />,
    );
    expect(screen.getByText(/blocked/i)).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: /metric\(s\) not found/i }));
    expect(onSelect).toHaveBeenCalledWith("sections[0].entries[0].bullets[1]");
  });
});
