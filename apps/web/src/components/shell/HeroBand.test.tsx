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

  it("glow tone is a faint wash: no shapes, no motif, centred children, the page's section gap below", () => {
    const { container } = render(<HeroBand tone="glow"><h1>x</h1></HeroBand>);
    const band = screen.getByTestId("hero-band");
    expect(band.className).toContain("bg-hero-glow");
    expect(band.className).toContain("border-b-0");
    expect(band.className).toContain("mb-16");
    expect(band.className).toContain("sm:mb-20");
    expect(container.querySelector("svg")).toBeNull();
    expect(container.querySelector("[data-decor]")).toBeNull();
    const inner = band.firstElementChild as HTMLElement;
    for (const c of ["mx-auto", "max-w-5xl", "items-center", "text-center"]) expect(inner.className).toContain(c);
  });

  it("other tones keep the left-aligned max-w-6xl content, the stitch motif and mb-8", () => {
    const { container } = render(<HeroBand tone="peach"><h1>x</h1></HeroBand>);
    const band = screen.getByTestId("hero-band");
    const inner = band.lastElementChild as HTMLElement;
    expect(inner.className).toContain("max-w-6xl");
    expect(inner.className).not.toContain("text-center");
    expect(band.className).toContain("mb-8");
    expect(container.querySelector("svg")).not.toBeNull();
  });
});
