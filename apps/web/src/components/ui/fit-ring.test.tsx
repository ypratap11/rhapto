import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { FitRing, fitBand } from "./fit-ring";

describe("fitBand", () => {
  it("bands on 75 and 60", () => {
    expect(fitBand(75)).toBe("high");
    expect(fitBand(74)).toBe("mid");
    expect(fitBand(60)).toBe("mid");
    expect(fitBand(59)).toBe("low");
    expect(fitBand(null)).toBe("none");
  });
});

describe("FitRing", () => {
  it("labels a scored ring and shows the number", () => {
    render(<FitRing fit={82} />);
    const ring = screen.getByRole("img", { name: "Fit 82" });
    expect(ring).toHaveAttribute("data-band", "high");
    expect(ring).toHaveTextContent("82");
  });

  it("shows an em dash and a not-scored label when the fit is null", () => {
    render(<FitRing fit={null} />);
    const ring = screen.getByRole("img", { name: /not scored yet/i });
    expect(ring).toHaveAttribute("data-band", "none");
    expect(ring).toHaveTextContent("—");
  });
});
