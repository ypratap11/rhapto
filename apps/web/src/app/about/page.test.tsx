import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import AboutPage from "./page";

describe("AboutPage", () => {
  it("leads with what Rhapto is and a way in", () => {
    render(<AboutPage />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "Every application, stitched to fit.",
    );
    expect(screen.getByRole("link", { name: /get started/i })).toHaveAttribute("href", "/settings");
  });

  it("lays out exactly five numbered steps in order", () => {
    render(<AboutPage />);
    const steps = within(screen.getByRole("list", { name: /how it works/i })).getAllByRole(
      "listitem",
    );
    expect(steps.map((li) => li.querySelector("[data-slot=card-title]")?.textContent)).toEqual([
      "Connect",
      "Bring your resume",
      "Pick a track",
      "Let the jobs come to you",
      "Tailor, review, apply",
    ]);
  });

  it("states the three guarantees that are the reason to use it", () => {
    render(<AboutPage />);
    expect(screen.getByText("Every line has a source")).toBeInTheDocument();
    expect(screen.getByText("Numbers need your sign-off")).toBeInTheDocument();
    expect(screen.getByText("The last click is yours")).toBeInTheDocument();
  });

  it("says what a resume costs before anyone spends money", () => {
    // The project funds nobody's API usage, so the price belongs on the way in, not in a FAQ.
    render(<AboutPage />);
    const costs = screen.getByText("What it costs").closest("[data-slot=card]");
    expect(costs).not.toBeNull();
    expect(costs).toHaveTextContent(/19¢/);
    expect(costs).toHaveTextContent(/AGPL-3\.0/);
  });

  it("promises in plain words that it never submits an application", () => {
    render(<AboutPage />);
    expect(screen.getByText(/Submit an application/i)).toBeInTheDocument();
  });
});
