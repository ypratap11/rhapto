import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { HeroBand } from "./HeroBand";

describe("HeroBand", () => {
  it("tints by tone, takes the tall height on request, and hides the motif from readers", () => {
    const { container } = render(
      <HeroBand tone="peach" height="tall">
        <h1>3 new roles fit you this week</h1>
      </HeroBand>,
    );
    const band = screen.getByTestId("hero-band");
    expect(band.className).toContain("bg-band-peach");
    expect(band.className).toContain("min-h-band-tall");
    expect(container.querySelector("svg")).toHaveAttribute("aria-hidden", "true");
  });

  it("defaults to the short band", () => {
    render(<HeroBand tone="mint">band</HeroBand>);
    expect(screen.getByTestId("hero-band").className).toContain("min-h-band-short");
  });
});
