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
    // Breakout classes for the full-bleed background (jsdom can't compute layout, so this only
    // proves the classes are present, not that they render edge-to-edge — see HeroBand.tsx's
    // comment; visual confirmation is a screenshot-pass concern).
    expect(band.className).toContain("w-screen");
    expect(band.className).toContain("mx-[calc(50%-50vw)]");
    expect(container.querySelector("svg")).toHaveAttribute("aria-hidden", "true");
  });

  it("defaults to the short band", () => {
    render(<HeroBand tone="mint">band</HeroBand>);
    expect(screen.getByTestId("hero-band").className).toContain("min-h-band-short");
  });

  it("glow tone paints the radial glow with two decorative shapes instead of the stitch motif", () => {
    const { container } = render(<HeroBand tone="glow"><h1>x</h1></HeroBand>);
    const band = screen.getByTestId("hero-band");
    expect(band.className).toContain("bg-hero-glow");
    expect(container.querySelector("svg")).toBeNull();
    const shapes = container.querySelectorAll("[data-decor]");
    expect(shapes).toHaveLength(2);
    shapes.forEach((s) => {
      expect(s).toHaveAttribute("aria-hidden", "true");
      expect(s.className).toContain("pointer-events-none");
    });
    expect(shapes[0]!.className).toContain("bg-decor-amber");
    expect(shapes[0]!.className).toContain("opacity-20");
    expect(shapes[1]!.className).toContain("bg-decor-teal");
    expect(shapes[1]!.className).toContain("opacity-15");
  });
});
