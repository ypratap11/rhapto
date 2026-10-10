import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import HomePage from "./page";

describe("HomePage", () => {
  it("renders the light landing at /, not the dashboard and not the full pitch", () => {
    render(<HomePage />);
    const ctas = screen.getAllByRole("link", { name: /tailor my resume|get started/i });
    expect(ctas.length).toBeGreaterThanOrEqual(1);
    for (const a of ctas) expect(a.getAttribute("href")).toBe(ctas[0]!.getAttribute("href"));
    // About-only content (the six-beat walkthrough's heading) must not be here, and neither may the
    // dashboard's search card, which would mean / regressed to mounting DashboardPage.
    expect(screen.queryByRole("heading", { name: "How it works" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /find your next role/i })).not.toBeInTheDocument();
  });
});
