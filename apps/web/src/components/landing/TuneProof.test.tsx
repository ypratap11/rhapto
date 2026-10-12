import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AI_DRAFT, RHAPTO_GIVES, TuneProof, YOUR_RESUME } from "./TuneProof";

describe("TuneProof, the hero's proof box", () => {
  it("shares its two engine-checked sentences byte for byte with the API test", () => {
    // apps/api/tests/unit/test_guardrails_tune.py pins both against the real engine.
    expect(AI_DRAFT).toBe("Moved 45 teams onto Snowflake and cut data-platform cost 30%.");
    expect(RHAPTO_GIVES).toBe("Moved 12 teams onto Snowflake and cut data-platform cost 30%.");
    expect(YOUR_RESUME).toBe("Led the Snowflake migration for 12 teams, cutting warehouse cost 30%.");
  });

  it("shows three rows in reading order, with real text for labels, sentences and tags", () => {
    const { container } = render(<TuneProof />);
    const rows = Array.from(container.querySelectorAll("[data-proof-row]"));
    expect(rows.map((r) => r.getAttribute("data-proof-row"))).toEqual(["resume", "draft", "gives"]);
    const text = rows.map((r) => r.textContent ?? "");
    expect(text[0]).toContain("Your resume");
    expect(text[0]).toContain(YOUR_RESUME);
    expect(text[1]).toContain("AI draft");
    expect(text[1]).toContain(AI_DRAFT);
    expect(text[1]).toContain("Stopped");
    expect(text[1]).toContain("45 is not in your resume.");
    expect(text[2]).toContain("Rhapto gives");
    expect(text[2]).toContain(RHAPTO_GIVES);
    expect(text[2]).toContain("Tailored, true");
    expect(screen.getByText("Stopped")).toBeInTheDocument();
    expect(screen.getByText("Tailored, true")).toBeInTheDocument();
  });

  it("marks 12 teams softly in the resume, 45 teams as the stop and 12 teams as the fix", () => {
    const { container } = render(<TuneProof />);
    const marks = Array.from(container.querySelectorAll("mark"));
    expect(marks.map((m) => m.textContent)).toEqual(["12 teams", "45 teams", "12 teams"]);
    expect(marks[1]!.className).toContain("bg-destructive");
    expect(marks[2]!.className).toContain("bg-fit-high-bg");
  });

  it("hides decorative icons, adds no role=img or aria-label, and is an opaque card", () => {
    const { container } = render(<TuneProof />);
    expect(container.querySelector("[role='img']")).toBeNull();
    expect(container.querySelector("[aria-label]")).toBeNull();
    const svgs = Array.from(container.querySelectorAll("svg, [data-icon]"));
    expect(svgs.length).toBeGreaterThan(0);
    for (const s of svgs) expect(s.getAttribute("aria-hidden")).toBe("true");
    expect((container.firstElementChild as HTMLElement).className).toContain("bg-surface");
    expect((container.firstElementChild as HTMLElement).className).toContain("max-w-3xl");
  });

  it("stacks on phones and lets sentences wrap", () => {
    const { container } = render(<TuneProof />);
    const row = container.querySelector("[data-proof-row]") as HTMLElement;
    expect(row.className).toContain("sm:grid-cols-");
    for (const s of Array.from(container.querySelectorAll("[data-proof-sentence]"))) {
      expect(s.className).toContain("min-w-0");
      expect(s.className).toContain("break-words");
    }
  });

  it("uses plain words: no rule ids, paths, jargon, provenance or absolute claims", () => {
    const { container } = render(<TuneProof />);
    const text = container.textContent ?? "";
    for (const jargon of ["no-new-numbers", "edits[0]", "number(s) not found", "guardrail", "rule fired"]) expect(text).not.toContain(jargon);
    expect(text).not.toMatch(/provenance|no-unverified-metrics/);
    expect(text).not.toMatch(/never|cannot happen|every catch/i);
    expect(text).not.toMatch(/\b(only|first)\b/i);
  });
});
