import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import HelpPage, { metadata } from "./page";

describe("/help", () => {
  it("has the title Help", () => {
    expect(metadata.title).toBe("Help");
  });

  it("renders eight closed questions and a way back", () => {
    const { container, getByRole } = render(<HelpPage />);
    expect(getByRole("heading", { level: 1, name: "Help" })).toBeInTheDocument();
    const details = container.querySelectorAll("details");
    expect(details).toHaveLength(8);
    for (const d of details) {
      expect(d.hasAttribute("open")).toBe(false);
      expect(d.querySelector("summary")!.className).toContain("min-h-11");
    }
    const back = getByRole("link", { name: "Back to Rhapto" });
    expect(back).toHaveAttribute("href", "/");
    expect(back.className).toContain("min-h-11");
  });

  it("uses plain words: none of the banned terms", () => {
    const { container } = render(<HelpPage />);
    expect(container.textContent).not.toMatch(/\b(only|first|best|fastest|block|track|guardrail|LLM|token|package)\b/i);
  });

  it("states both tailoring modes honestly and names no free-run number", () => {
    const text = render(<HelpPage />).container.textContent ?? "";
    expect(text).toMatch(/Light touch/);
    expect(text).toMatch(/Full rewrite/);
    expect(text).toMatch(/Your experience/);
    expect(text).toMatch(/Download my data/);
    expect(text).toMatch(/Send feedback/);
    expect(text).not.toMatch(/\b\d+ (free|resumes)/i);
  });
});
