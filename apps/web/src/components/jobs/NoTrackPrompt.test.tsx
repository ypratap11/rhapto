import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { NoTrackPrompt } from "./NoTrackPrompt";

describe("NoTrackPrompt", () => {
  it("asks for a role, links to the role picker and labels the list as unranked", () => {
    render(<NoTrackPrompt />);
    expect(screen.getByText(/pick the role you want and we.ll rank these for you/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Pick a role" })).toHaveAttribute("href", "/profile?card=tracks");
    expect(screen.getByText("Newest jobs, not ranked yet")).toBeInTheDocument();
  });
});
