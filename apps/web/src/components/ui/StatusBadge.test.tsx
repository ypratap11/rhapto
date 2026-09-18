import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StatusBadge } from "./StatusBadge";

describe("StatusBadge", () => {
  it("paints every tone from design tokens, never a raw palette class", () => {
    for (const tone of ["neutral", "muted", "high", "mid", "primary", "danger"] as const) {
      const { unmount } = render(<StatusBadge tone={tone}>{tone}</StatusBadge>);
      const className = screen.getByText(tone).className;
      expect(className).not.toMatch(/(bg|text|border)-(red|amber|green|zinc|slate|indigo)-\d+/);
      expect(className).toMatch(/(surface-muted|fit-high|fit-mid|primary|destructive)/);
      unmount();
    }
  });
});
