import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { DashboardSavedSearch } from "@/lib/api/queries";
import { SavedSearchesRail } from "./SavedSearchesRail";

const searches: DashboardSavedSearch[] = [
  { id: "s1", name: "PM roles", new_count: 4 },
  { id: "s2", name: "Data roles", new_count: 0 },
];

describe("SavedSearchesRail", () => {
  it("links each search to its results and shows the new-count badge only when positive", () => {
    render(<SavedSearchesRail searches={searches} />);
    expect(screen.getByRole("link", { name: /pm roles/i })).toHaveAttribute("href", "/jobs?search_id=s1");
    expect(screen.getByText("4 new")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /data roles/i })).toHaveAttribute("href", "/jobs?search_id=s2");
    expect(screen.queryByText("0 new")).not.toBeInTheDocument();
  });

  it("says there's nothing saved yet when the list is empty", () => {
    render(<SavedSearchesRail searches={[]} />);
    expect(screen.getByText(/save a search/i)).toBeInTheDocument();
  });
});
