import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { TuneProof } from "./TuneProof";

describe("TuneProof", () => {
  it("says in plain words what was stopped, with no rule ids or paths on the homepage", () => {
    // The catch itself (the engine rejects 45 in this sentence) is still pinned by
    // apps/api/tests/unit/test_guardrails_tune.py::test_homepage_proof_matches_the_engine_wording.
    const { container } = render(<TuneProof />);
    expect(screen.getByText("Rhapto stopped this draft: 45 is not in your resume.")).toBeInTheDocument();
    expect(screen.getByText(/Led the Snowflake migration for 12 teams, cutting warehouse cost 30%\./)).toBeInTheDocument();
    const text = container.textContent ?? "";
    for (const jargon of ["no-new-numbers", "edits[0]", "number(s) not found", "guardrail", "rule fired"]) expect(text).not.toContain(jargon);
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
