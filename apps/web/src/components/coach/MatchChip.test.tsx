import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MatchChip } from "./MatchChip";

describe("MatchChip", () => {
  it("draws Strong match on the teal fit colours", () => {
    render(<MatchChip label="Strong match" />);
    const cls = screen.getByText("Strong match").className;
    expect(cls).toContain("bg-fit-high-bg");
    expect(cls).toContain("text-fit-high");
    expect(cls).toContain("rounded-full");
  });
  it("draws Good match on the muted surface", () => {
    render(<MatchChip label="Good match" />);
    const cls = screen.getByText("Good match").className;
    expect(cls).toContain("bg-surface-muted");
    expect(cls).toContain("text-muted-foreground");
  });
});
