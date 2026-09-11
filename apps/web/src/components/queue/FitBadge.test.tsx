import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { FitBadge } from "./FitBadge";

describe("FitBadge", () => {
  it("shows score and track, and a scoring placeholder when unscored", () => {
    render(<FitBadge fit={82} trackName="Data PM" minFit={60} />);
    expect(screen.getByText("82")).toBeInTheDocument();
    expect(screen.getByText("Data PM")).toBeInTheDocument();
    render(<FitBadge fit={null} trackName={null} minFit={null} />);
    expect(screen.getByText(/scoring/i)).toBeInTheDocument();
  });
});
