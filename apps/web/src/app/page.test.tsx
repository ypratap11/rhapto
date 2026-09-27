import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import HomePage from "./page";

describe("HomePage", () => {
  it("renders the landing pitch at /, not the dashboard", () => {
    render(<HomePage />);
    // "How it works" and the six beat titles are Landing-only content -- the dashboard has no
    // section by that name, so this fails if / ever regresses back to mounting the dashboard.
    // Re-pointed from the five "How it works" card titles, which were removed as a second, weaker
    // telling of the same journey; the beats are now the only place it is told. They are spans
    // inside each beat's button, not headings, so they are asserted on by text.
    expect(screen.getByRole("heading", { name: "How it works" })).toBeInTheDocument();
    expect(screen.getByText("You ask for access")).toBeInTheDocument();
    expect(screen.getByText("You bring your resume")).toBeInTheDocument();
    expect(screen.getByText("You pick a track")).toBeInTheDocument();
    expect(screen.getByText("Jobs arrive and get scored")).toBeInTheDocument();
    expect(screen.getByText("Rhapto tailors one")).toBeInTheDocument();
    expect(screen.getByText("You review and send it")).toBeInTheDocument();
    // Dashboard-only content (its search card heading) must not be here -- a regression back to
    // mounting DashboardPage at / would otherwise still pass the assertions above, since Landing
    // is also linked from the Dashboard-era Connect card in some code paths.
    expect(screen.queryByRole("heading", { name: /find your next role/i })).not.toBeInTheDocument();
  });
});
