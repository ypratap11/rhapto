import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { CoachFrame } from "./CoachFrame";

it("leads back to the dashboard, not 'the full app'", () => {
  render(
    <CoachFrame title="Tailor a resume">
      <p>x</p>
    </CoachFrame>,
  );
  expect(screen.getByRole("link", { name: "Back to your dashboard" })).toHaveAttribute("href", "/dashboard");
  expect(screen.queryByText(/skip to the full app/i)).toBeNull();
});
