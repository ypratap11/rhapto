import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import HomePage from "./page";

describe("HomePage", () => {
  it("renders the landing pitch at /, not the dashboard", () => {
    render(<HomePage />);
    // "How it works" and its five step titles are Landing-only content -- the dashboard has no
    // section by that name, so this fails if / ever regresses back to mounting the dashboard. The
    // step titles are `CardTitle`s (a styled `div`, not a heading element), so they are asserted
    // on by text rather than heading role.
    expect(screen.getByRole("heading", { name: "How it works" })).toBeInTheDocument();
    expect(screen.getByText("Get in")).toBeInTheDocument();
    expect(screen.getByText("Bring your resume")).toBeInTheDocument();
    expect(screen.getByText("Pick a track")).toBeInTheDocument();
    expect(screen.getByText("Let the jobs come to you")).toBeInTheDocument();
    expect(screen.getByText("Tailor, review, apply")).toBeInTheDocument();
    // Dashboard-only content (its search card heading) must not be here -- a regression back to
    // mounting DashboardPage at / would otherwise still pass the assertions above, since Landing
    // is also linked from the Dashboard-era Connect card in some code paths.
    expect(screen.queryByRole("heading", { name: /find your next role/i })).not.toBeInTheDocument();
  });
});
