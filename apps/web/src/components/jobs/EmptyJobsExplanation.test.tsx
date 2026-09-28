import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { JobsEmptyReason } from "@/lib/jobs-empty";
import { DEFAULT_SEARCH_STATE, type SearchState } from "@/lib/search-state";
import { EmptyJobsExplanation } from "./EmptyJobsExplanation";

/**
 * Every fixture below is a response shape the API really produces, and every assertion is about a
 * string the RESPONSE supplied — a field display name, a location, a count. Nothing asserted here is
 * a literal in the component, because an assertion about the component's own literal proves the
 * component renders a string, not that the condition was detected.
 *
 * Each case is rendered with two different fixtures for exactly that reason: the output has to track
 * the fixture.
 */
const reason = (over: Partial<JobsEmptyReason>): JobsEmptyReason => ({
  total: 12,
  cause: "filter",
  filter_id: null,
  filter_value: null,
  would_match: null,
  field_name: null,
  user_field_names: [],
  search_name: null,
  search_location: null,
  search_runs: null,
  search_ever_found: null,
  ...over,
});

function setup(props: Partial<Parameters<typeof EmptyJobsExplanation>[0]> = {}) {
  const onChange = vi.fn<(next: SearchState) => void>();
  const onClearSavedSearch = vi.fn();
  render(
    <EmptyJobsExplanation
      reason={null}
      state={DEFAULT_SEARCH_STATE}
      onChange={onChange}
      onClearSavedSearch={onClearSavedSearch}
      {...props}
    />,
  );
  return { onChange, onClearSavedSearch };
}

describe("EmptyJobsExplanation, a field with no tracks", () => {
  it("names the field asked for and the fields the user actually has", () => {
    setup({
      reason: reason({
        cause: "field_without_tracks",
        field_name: "Engineering",
        user_field_names: ["Program and Project Management"],
      }),
    });
    expect(screen.getByText(/no tracks in Engineering/i)).toBeInTheDocument();
    expect(screen.getByText(/Program and Project Management/)).toBeInTheDocument();
  });

  it("tracks the fixture rather than a literal", () => {
    // Two other taxonomy names, supplied by the response. If the component held either string, one
    // of these two tests would be impossible to satisfy.
    setup({
      reason: reason({
        cause: "field_without_tracks",
        field_name: "Design",
        user_field_names: ["Data Science", "Finance"],
      }),
    });
    expect(screen.getByText(/no tracks in Design/i)).toBeInTheDocument();
    expect(screen.getByText(/Data Science and Finance/)).toBeInTheDocument();
    expect(screen.queryByText(/Engineering/)).not.toBeInTheDocument();
  });

  it("does not claim the user has tracks somewhere when they have none at all", () => {
    setup({ reason: reason({ cause: "field_without_tracks", field_name: "Design", user_field_names: [] }) });
    expect(screen.getByText(/no tracks at all yet/i)).toBeInTheDocument();
  });
});

describe("EmptyJobsExplanation, a filter that excluded everything", () => {
  it("names the date filter and widens it to any", async () => {
    const { onChange } = setup({
      reason: reason({ cause: "filter", filter_id: "posted_within", filter_value: "24h", would_match: 10 }),
    });
    expect(screen.getByText(/date filter excluded everything/i)).toBeInTheDocument();
    expect(screen.getByText(/10 jobs would show/i)).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: /any posting date/i }));
    expect(onChange).toHaveBeenCalledWith({ ...DEFAULT_SEARCH_STATE, posted_within: "any" });
  });

  it("widens the source filter differently, from the same component", async () => {
    // The contrasting fixture: a different `filter_id` must produce a different widen call, which is
    // what proves the widen came from the response and not from one hard-coded branch.
    const state: SearchState = { ...DEFAULT_SEARCH_STATE, sources: ["adzuna"] };
    const { onChange } = setup({
      state,
      reason: reason({ cause: "filter", filter_id: "sources", filter_value: "adzuna", would_match: 10 }),
    });
    expect(screen.getByText(/source filter excluded everything/i)).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: /clear the source filter/i }));
    expect(onChange).toHaveBeenCalledWith({ ...state, sources: [] });
  });

  it("offers to include hidden jobs when the hidden switch is what excluded them", async () => {
    const { onChange } = setup({
      reason: reason({ cause: "filter", filter_id: "hidden", filter_value: "false", would_match: 4 }),
    });
    expect(screen.getByText(/4 jobs would show/i)).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: /include hidden jobs/i }));
    expect(onChange).toHaveBeenCalledWith({ ...DEFAULT_SEARCH_STATE, hidden: true });
  });

  it("reports one job in the singular", () => {
    setup({ reason: reason({ cause: "filter", filter_id: "posted_within", filter_value: "7d", would_match: 1 }) });
    expect(screen.getByText(/1 job would show/i)).toBeInTheDocument();
  });
});

describe("EmptyJobsExplanation, a combination", () => {
  it("blames nobody and offers to clear everything", async () => {
    const state: SearchState = { ...DEFAULT_SEARCH_STATE, sources: ["adzuna"], posted_within: "24h" };
    const { onChange } = setup({ state, reason: reason({ cause: "combination", filter_id: null }) });
    expect(screen.getByText(/all of these filters together/i)).toBeInTheDocument();
    // No filter is named, because none is responsible.
    expect(screen.queryByText(/excluded everything/i)).not.toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: /clear all filters/i }));
    expect(onChange).toHaveBeenCalledWith({ ...state, sources: [], posted_within: "any", field: null, hidden: false, fit: "all" });
  });
});

describe("EmptyJobsExplanation, a saved search", () => {
  it("says how many times it has run and never returned a job, and shows its own location", () => {
    setup({
      reason: reason({
        cause: "filter",
        filter_id: "search_id",
        search_name: "Bay Area PM",
        search_location: "San Francisco Bay Area",
        search_runs: 3,
        search_ever_found: false,
      }),
    });
    expect(screen.getByText(/Bay Area PM has run 3 times and never returned a job/i)).toBeInTheDocument();
    expect(screen.getByText(/San Francisco Bay Area/)).toBeInTheDocument();
  });

  it("does not assert a cause for the zero, and never suggests another location", () => {
    // Condition C7 on the rendering side. Nothing distinguishes an unrecognised location from a
    // narrow query from an empty market, so no wording here may claim one -- and there is no
    // gazetteer to draw an alternative from, so "Try X" cannot be produced honestly.
    const { container } = render(
      <EmptyJobsExplanation
        reason={reason({
          cause: "filter",
          filter_id: "search_id",
          search_name: "Bay Area PM",
          search_location: "San Francisco Bay Area",
          search_runs: 3,
          search_ever_found: false,
        })}
        state={DEFAULT_SEARCH_STATE}
        onChange={vi.fn()}
        onClearSavedSearch={vi.fn()}
      />,
    );
    const text = container.textContent ?? "";
    expect(text).not.toMatch(/may not be recognised|not recognised|unrecognised/i);
    expect(text).not.toMatch(/\btry ['"]/i);
  });

  it("says it has not run yet when it never has, which is a different thing", () => {
    setup({
      reason: reason({
        cause: "filter",
        filter_id: "search_id",
        search_name: "Nowhere roles",
        search_location: "Nowhereville",
        search_runs: 0,
        search_ever_found: false,
      }),
    });
    expect(screen.getByText(/Nowhere roles has not run yet/i)).toBeInTheDocument();
    expect(screen.queryByText(/never returned a job/i)).not.toBeInTheDocument();
  });

  it("falls through to the generic filter wording once the search has matched before", () => {
    // The third state: it HAS found things, so today's zero is "nothing new" — not "never matched".
    setup({
      reason: reason({
        cause: "filter",
        filter_id: "search_id",
        filter_value: "s1",
        would_match: 6,
        search_name: "Bay Area PM",
        search_runs: 9,
        search_ever_found: true,
      }),
    });
    expect(screen.queryByText(/never returned a job/i)).not.toBeInTheDocument();
    expect(screen.getByText(/saved search filter excluded everything/i)).toBeInTheDocument();
  });

  it("clears the saved search by navigation, not by a state change", async () => {
    const { onChange, onClearSavedSearch } = setup({
      reason: reason({ cause: "filter", filter_id: "search_id", filter_value: "s1", would_match: 6, search_ever_found: true }),
    });
    await userEvent.setup().click(screen.getByRole("button", { name: /show all jobs/i }));
    expect(onClearSavedSearch).toHaveBeenCalledTimes(1);
    expect(onChange).not.toHaveBeenCalled();
  });
});

describe("EmptyJobsExplanation, the client's own fit filter", () => {
  it("explains it here rather than asking the server, because this is the layer that applies it", async () => {
    const state: SearchState = { ...DEFAULT_SEARCH_STATE, fit: "75" };
    const { onChange } = setup({ state, fitHiddenCount: 14, reason: null });
    expect(screen.getByText(/14 jobs hidden by the fit filter/i)).toBeInTheDocument();
    expect(screen.getByText(/scores 75 or above/i)).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: /show any fit/i }));
    expect(onChange).toHaveBeenCalledWith({ ...state, fit: "all" });
  });

  it("tracks the count and the threshold from the fixture", () => {
    setup({ state: { ...DEFAULT_SEARCH_STATE, fit: "60" }, fitHiddenCount: 2, reason: null });
    expect(screen.getByText(/2 jobs hidden by the fit filter/i)).toBeInTheDocument();
    expect(screen.getByText(/scores 60 or above/i)).toBeInTheDocument();
  });

  it("wins over a stale server reason, since the grid was not actually empty upstream", () => {
    setup({ fitHiddenCount: 3, reason: reason({ cause: "no_jobs" }) });
    expect(screen.getByText(/3 jobs hidden by the fit filter/i)).toBeInTheDocument();
    expect(screen.queryByText(/Rhapto has not found anything/i)).not.toBeInTheDocument();
  });
});

describe("EmptyJobsExplanation, the other causes", () => {
  it("points a brand-new account at Settings when it owns no jobs at all", () => {
    setup({ reason: reason({ cause: "no_jobs", total: 0 }) });
    expect(screen.getByText(/Rhapto has not found anything/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /open settings/i })).toHaveAttribute("href", "/settings");
  });

  it("shows a placeholder while the diagnosis is in flight rather than a cause it does not have", () => {
    setup({ loading: true, reason: null });
    expect(screen.getByTestId("empty-reason-loading")).toBeInTheDocument();
    expect(screen.queryByTestId("empty-jobs-explanation")).not.toBeInTheDocument();
  });

  it("falls back to the plain empty state when there is no diagnosis", () => {
    setup({ reason: null });
    expect(screen.getByText(/no jobs yet/i)).toBeInTheDocument();
    expect(screen.queryByTestId("empty-jobs-explanation")).not.toBeInTheDocument();
  });

  it("does not dress up nothing_matched as a problem", () => {
    setup({ reason: reason({ cause: "nothing_matched" }) });
    expect(screen.getByText(/no jobs yet/i)).toBeInTheDocument();
  });
});
