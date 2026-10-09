import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { TuneProof } from "./TuneProof";

describe("TuneProof", () => {
  it("proof_quotes_the_tune_rule_exactly", () => {
    // Quoted from apps/api/src/rhapto/engine/guardrails/tune.py (NO_NEW_NUMBERS, the violation path
    // and message). apps/api/tests/unit/test_guardrails_tune.py::test_homepage_proof_matches_the_engine_wording
    // pins the same four strings against the engine: change the engine wording and both fail.
    render(<TuneProof />);
    expect(screen.getByText("no-new-numbers")).toBeInTheDocument();
    expect(screen.getByText("edits[0]")).toBeInTheDocument();
    expect(screen.getByText("number(s) not found in the document: 45")).toBeInTheDocument();
    expect(screen.getByText(/Led the Snowflake migration for 12 teams, cutting warehouse cost 30%\./)).toBeInTheDocument();
  });

  it("does not advertise rules the coach path never runs", () => {
    const { container } = render(<TuneProof />);
    const text = container.textContent ?? "";
    expect(text).not.toMatch(/provenance|no-unverified-metrics/);
    // And it says nothing stronger than what happens inside a run.
    expect(text).toMatch(/sent back for one fix/i);
    expect(text).not.toMatch(/never|cannot happen|every catch/i);
  });

  it("highlights the invented number in the model's draft", () => {
    const { container } = render(<TuneProof />);
    expect(container.querySelector("mark")?.textContent).toBe("45");
  });
});
