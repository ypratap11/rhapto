import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ProfileChecklist } from "./ProfileChecklist";

const checklist = {
  resume_template: true,
  contact_answers: false,
  tracks: true,
  blocks_verified: false,
  guardrails: true,
  location_preferences: false,
  verified_blocks: 18,
  total_blocks: 23,
};

describe("ProfileChecklist", () => {
  it("shows all six rows, the verified count, and an Edit deep link per row", () => {
    render(<ProfileChecklist checklist={checklist} />);
    const rows = screen.getAllByRole("listitem");
    expect(rows).toHaveLength(6);
    expect(screen.getByText("18 of 23 verified")).toBeInTheDocument();
    expect(within(rows[0]!).getByRole("link", { name: /edit/i })).toHaveAttribute("href", "/profile?card=resume-template");
    expect(within(rows[1]!).getByRole("link", { name: /edit/i })).toHaveAttribute("href", "/profile?card=answers");
    expect(within(rows[5]!).getByRole("link", { name: /edit/i })).toHaveAttribute("href", "/profile?card=location");
  });

  it("marks done and not-done rows for a screen reader", () => {
    render(<ProfileChecklist checklist={checklist} />);
    expect(screen.getAllByRole("listitem")[0]).toHaveAttribute("data-done", "true");
    expect(screen.getAllByRole("listitem")[1]).toHaveAttribute("data-done", "false");
  });

  it("shows a loading skeleton instead of a false 'not done' row while the checklist is still in flight", () => {
    // A loading `checklist={null}` and a settled-but-missing one must not look the same: this one
    // renders a skeleton, not silently nothing, and never claims "18 of 23 verified" or a "not
    // done" icon for data it hasn't seen yet.
    render(<ProfileChecklist checklist={null} loading />);
    expect(screen.getByTestId("checklist-skeleton")).toBeInTheDocument();
    expect(screen.queryByText("18 of 23 verified")).not.toBeInTheDocument();
    expect(screen.queryAllByRole("listitem")).toHaveLength(0);
  });

  it("renders nothing when settled with no checklist to show (not loading, no data)", () => {
    const { container } = render(<ProfileChecklist checklist={null} />);
    expect(container).toBeEmptyDOMElement();
  });
});
