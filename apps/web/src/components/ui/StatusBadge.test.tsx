import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StatusBadge } from "./StatusBadge";
import type { Tone } from "@/lib/status";

// The exact class fragment each tone must paint with (mirrors StatusBadge's own TONE_CLASS map).
// Asserting the tone-specific fragment, not just "some token-looking class exists", matters
// because Badge's base classes always contain the literal substring `aria-invalid:border-
// destructive` (see badge.tsx) -- a regex that only checks for that substring would pass even if
// a tone's own mapping were missing or wrong.
const EXPECTED_CLASS: Record<Tone, string> = {
  neutral: "rounded-chip border-border bg-surface-muted text-foreground",
  muted: "rounded-chip border-border bg-surface-muted text-muted-foreground",
  high: "rounded-chip border-fit-high/30 bg-fit-high-bg text-fit-high",
  mid: "rounded-chip border-fit-mid/30 bg-fit-mid-bg text-fit-mid",
  primary: "rounded-chip border-primary/30 bg-primary/10 text-primary",
  danger: "rounded-chip border-destructive/30 bg-destructive/10 text-destructive",
};

describe("StatusBadge", () => {
  it("paints every tone from design tokens, never a raw palette class", () => {
    for (const tone of ["neutral", "muted", "high", "mid", "primary", "danger"] as const) {
      const { unmount } = render(<StatusBadge tone={tone}>{tone}</StatusBadge>);
      const className = screen.getByText(tone).className;
      expect(className).not.toMatch(/(bg|text|border)-(red|amber|green|zinc|slate|indigo)-\d+/);
      expect(className).toContain(EXPECTED_CLASS[tone]);
      unmount();
    }
  });
});
