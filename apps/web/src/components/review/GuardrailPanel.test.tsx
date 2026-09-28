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

const ERROR_VIOLATION = {
  rule: "no-unverified-metrics",
  severity: "error" as const,
  message: "metric(s) not found: 25%",
  path: "sections[0].entries[0].bullets[1]",
  block_id: "acme-migration",
};

const REMEDY = "Mark the block holding that figure as verified, or regenerate so the bullet stops asserting it.";

describe("GuardrailPanel, what to do about it", () => {
  it("shows the severity, the block it came from, and the remedy for the rule", () => {
    render(
      <GuardrailPanel
        report={{ passed: false, rules_run: ["provenance"], violations: [ERROR_VIOLATION] }}
        remedies={{ "no-unverified-metrics": REMEDY }}
        onSelect={vi.fn()}
      />,
    );
    expect(screen.getByText("error")).toBeInTheDocument();
    // The path says where the bullet is in the document; `block_id` says what to go and edit.
    expect(screen.getByText("acme-migration")).toBeInTheDocument();
    expect(screen.getByText(REMEDY)).toBeInTheDocument();
  });

  it("keeps a rule it has no remedy for fully readable", () => {
    // THE case a bare `remedies[v.rule]` rendered into the row would blank out: a rule added
    // server-side before this map knew it, or a historical report naming a rule this build dropped.
    // The row must still carry the rule id, the message and the bullet.
    render(
      <GuardrailPanel
        report={{
          passed: false,
          rules_run: ["some-future-rule"],
          violations: [{ ...ERROR_VIOLATION, rule: "some-future-rule" }],
        }}
        remedies={{ "no-unverified-metrics": REMEDY }}
        onSelect={vi.fn()}
      />,
    );
    const row = screen.getByRole("button", { name: /metric\(s\) not found/i });
    expect(row).toHaveTextContent("some-future-rule");
    expect(row).toHaveTextContent("metric(s) not found: 25%");
    expect(row).toHaveTextContent("sections[0].entries[0].bullets[1]");
    // And no remedy from some other rule leaks in.
    expect(screen.queryByText(REMEDY)).not.toBeInTheDocument();
  });

  it("distinguishes a warning from the error that blocked the package", () => {
    // Two violations of different severities in one report, so the assertion cannot pass on a
    // constant: a warning did not block anything and must not be dressed as though it had.
    render(
      <GuardrailPanel
        report={{
          passed: false,
          rules_run: ["provenance", "visibility-context"],
          violations: [
            ERROR_VIOLATION,
            { ...ERROR_VIOLATION, rule: "visibility-context", severity: "warning", message: "scope missing", path: "sections[1]" },
          ],
        }}
        remedies={{ "no-unverified-metrics": REMEDY }}
        onSelect={vi.fn()}
      />,
    );
    expect(screen.getByRole("button", { name: /metric\(s\) not found/i })).toHaveTextContent("error");
    expect(screen.getByRole("button", { name: /scope missing/i })).toHaveTextContent("warning");
  });

  it("renders without a remedies prop at all", () => {
    // An older API, or any caller that has not been updated: the panel must not crash or drop rows.
    render(
      <GuardrailPanel
        report={{ passed: false, rules_run: ["provenance"], violations: [ERROR_VIOLATION] }}
        onSelect={vi.fn()}
      />,
    );
    expect(screen.getByRole("button", { name: /metric\(s\) not found/i })).toHaveTextContent("no-unverified-metrics");
  });
});

