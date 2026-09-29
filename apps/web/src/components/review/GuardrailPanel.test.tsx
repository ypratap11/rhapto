import { render, screen, within } from "@testing-library/react";
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


describe("GuardrailPanel, a violation that names something absent from the document", () => {
  const COMPLETENESS = {
    rule: "completeness",
    severity: "error" as const,
    message: "role block 'role-e' (Vertex Robotics — Founder, 2023-Present) was selected but does not appear in Experience",
    path: "selection.block_ids['role-e']",
    block_id: "role-e",
  };
  const COMPLETENESS_REMEDY = "Every selected role, project and credential must keep an entry.";

  it("renders a plain row, not a dead button, and keeps the block id and remedy", () => {
    render(
      <GuardrailPanel
        report={{ passed: false, rules_run: ["provenance", "completeness"], violations: [COMPLETENESS] }}
        remedies={{ completeness: COMPLETENESS_REMEDY }}
        onSelect={vi.fn()}
      />,
    );
    expect(screen.getByText(/does not appear in Experience/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /does not appear in Experience/i })).not.toBeInTheDocument();
    // The row itself, not just "no button with that name": nothing in it is interactive.
    const item = screen.getByText(/does not appear in Experience/i).closest("li");
    expect(item).not.toBeNull();
    const row = item!.firstElementChild as HTMLElement;
    expect(row.tagName).toBe("DIV");
    expect(row).not.toHaveAttribute("role");
    expect(within(item!).queryByRole("button")).not.toBeInTheDocument();
    expect(within(item!).queryByRole("link")).not.toBeInTheDocument();
    expect(screen.getByText("role-e")).toBeInTheDocument();
    expect(screen.getByText(COMPLETENESS_REMEDY)).toBeInTheDocument();
  });

  it("links a node-less row to the package when given somewhere to go, still not as a button", () => {
    // The job page: its rows navigate to the package page, and a completeness row must too.
    render(
      <GuardrailPanel
        report={{ passed: false, rules_run: ["completeness"], violations: [ERROR_VIOLATION, COMPLETENESS] }}
        onSelect={vi.fn()}
        nodelessHref="/jobs/j1/packages/p1"
      />,
    );
    expect(screen.getByRole("link", { name: /does not appear in Experience/i })).toHaveAttribute("href", "/jobs/j1/packages/p1");
    expect(screen.queryByRole("button", { name: /does not appear in Experience/i })).not.toBeInTheDocument();
    // A row that addresses a node keeps its button.
    expect(screen.getByRole("button", { name: /metric\(s\) not found/i })).toBeInTheDocument();
  });

  it("does not take the button away from the paths that do address something", async () => {
    // The regression a blanket `startsWith("sections[")` rule would have caused: tune-mode
    // violations are `edits[i]`, and both pages route them through onSelect.
    const onSelect = vi.fn();
    const at = (path: string) => ({ ...ERROR_VIOLATION, message: `problem at ${path}`, path });
    render(
      <GuardrailPanel
        report={{
          passed: false,
          rules_run: ["tune-scope"],
          violations: [at("edits[0]"), at("summary[0]"), at("cover_note"), COMPLETENESS],
        }}
        onSelect={onSelect}
      />,
    );
    expect(screen.getAllByRole("button")).toHaveLength(3);
    await userEvent.setup().click(screen.getByRole("button", { name: /problem at edits\[0\]/ }));
    expect(onSelect).toHaveBeenCalledWith("edits[0]");
  });
});
