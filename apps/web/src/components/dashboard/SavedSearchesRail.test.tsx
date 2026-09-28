import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { DashboardSavedSearch } from "@/lib/api/queries";
import { SavedSearchesRail } from "./SavedSearchesRail";

// Two searches with contrasting histories, because both render a zero badge: "Data roles" has
// polled and never found a posting, which is a different thing to say than "nothing new".
const searches: DashboardSavedSearch[] = [
  { id: "s1", name: "PM roles", new_count: 4, ever_found: true },
  { id: "s2", name: "Data roles", new_count: 0, ever_found: false },
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

  it("shows a loading skeleton instead of the empty-state copy while the list is still in flight", () => {
    // An empty array is exactly what a caller has before the dashboard call resolves — without a
    // separate `loading` signal this and "you've never saved a search" render identically.
    render(<SavedSearchesRail searches={[]} loading />);
    expect(screen.getByTestId("saved-searches-skeleton")).toBeInTheDocument();
    expect(screen.queryByText(/save a search/i)).not.toBeInTheDocument();
  });

  it("says the saved searches failed to load instead of claiming there are none", () => {
    // Once a failed dashboard call settles, loading goes false with searches still []: the exact
    // shape "you've never saved a search" has. error must not fall through to that copy.
    render(<SavedSearchesRail searches={[]} error />);
    expect(screen.getByTestId("saved-searches-error")).toBeInTheDocument();
    expect(screen.getByText(/couldn.t load/i)).toBeInTheDocument();
    expect(screen.queryByText(/save a search from the jobs page/i)).not.toBeInTheDocument();
  });
});

describe("SavedSearchesRail, the silence at zero", () => {
  it("distinguishes a search with nothing new from one that has never matched", () => {
    // The rail hides its badge at zero, so both rows looked identical. "Data roles" has never
    // returned a job; that is a different thing to say, and `ever_found` is what says it.
    render(<SavedSearchesRail searches={searches} />);
    const never = screen.getByRole("link", { name: /data roles/i });
    const active = screen.getByRole("link", { name: /pm roles/i });
    expect(never).toHaveTextContent("Never matched");
    expect(active).not.toHaveTextContent("Never matched");
    expect(active).toHaveTextContent("4 new");
  });

  it("does not mark a search that has found jobs before but has nothing new right now", () => {
    render(<SavedSearchesRail searches={[{ id: "s3", name: "Quiet roles", new_count: 0, ever_found: true }]} />);
    const row = screen.getByRole("link", { name: /quiet roles/i });
    expect(row).not.toHaveTextContent("Never matched");
    expect(row).not.toHaveTextContent("new");
  });
});

