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
  // Empty by default: most causes have no leave-one-out map worth carrying, and a test that wants a
  // widen offered has to say so, which is the point of gating on it.
  would_match_without: {},
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
  it("says removing any single filter still leaves nothing, which is what the cause means", () => {
    // `combination` is returned when EVERY leave-one-out count is zero. The description therefore
    // has to say that removing any one filter changes nothing — the previous copy said the
    // opposite ("each filter on its own leaves something") and then advised widening them one at a
    // time, which cannot work for this cause by construction.
    setup({
      state: { ...DEFAULT_SEARCH_STATE, sources: ["adzuna"], posted_within: "24h" },
      reason: reason({ cause: "combination", filter_id: null, total: 12 }),
    });
    expect(screen.getByText(/all of these filters together/i)).toBeInTheDocument();
    expect(screen.getByText(/removing any single one of them still leaves nothing/i)).toBeInTheDocument();
    // And it must NOT claim the opposite.
    expect(screen.queryByText(/on its own leaves something/i)).not.toBeInTheDocument();
    // No filter is named, because none is responsible.
    expect(screen.queryByText(/excluded everything/i)).not.toBeInTheDocument();
  });

  it("counts the user's own jobs in the sentence, from the response", () => {
    // A second fixture with a different total, so the number cannot be a literal.
    setup({ reason: reason({ cause: "combination", filter_id: null, total: 1 }) });
    expect(screen.getByText(/you have 1 job, and none matches/i)).toBeInTheDocument();
  });

  it("does not promise the grid will fill, and clears only the filters", async () => {
    const state: SearchState = { ...DEFAULT_SEARCH_STATE, sources: ["adzuna"], posted_within: "24h" };
    const { onChange } = setup({ state, reason: reason({ cause: "combination", filter_id: null }) });
    await userEvent.setup().click(screen.getByRole("button", { name: /clear these filters/i }));
    // `hidden` is NOT touched. It is a mode, not a filter that can be absent: the API cannot express
    // "hidden and not hidden", so setting it to false picks the exclude-hidden side rather than
    // removing the constraint — which for an entirely-hidden corpus left the grid exactly as empty
    // with exactly the same message.
    expect(onChange).toHaveBeenCalledWith({ ...state, sources: [], posted_within: "any", field: null, fit: "all" });
  });

  it("offers the hidden toggle when the API says flipping it would reveal rows", async () => {
    // The dead end QA reproduced: a corpus that is entirely hidden and entirely over 90 days old.
    // Clearing the filters leaves it empty; flipping the mode is what reaches those rows — and the
    // leave-one-out count is how the client knows that, rather than guessing.
    const { onChange } = setup({
      reason: reason({ cause: "combination", filter_id: null, would_match_without: { hidden: 3 } }),
    });
    await userEvent.setup().click(screen.getByRole("button", { name: /include hidden jobs/i }));
    expect(onChange).toHaveBeenCalledWith({ ...DEFAULT_SEARCH_STATE, hidden: true });
  });

  it("does not offer the hidden toggle when flipping it would reveal nothing", () => {
    // Nothing is hidden, so the toggle would be inert. The client cannot know that from the state —
    // only from the count the server already computed, which is why it is on the wire.
    setup({ reason: reason({ cause: "combination", filter_id: null, would_match_without: { hidden: 0 } }) });
    expect(screen.queryByRole("button", { name: /hidden jobs/i })).not.toBeInTheDocument();
  });

  it("does not offer it when the API sent no counts at all", () => {
    // An older API, or a cause that carries no map: absent must mean "do not offer", not "offer".
    setup({ reason: reason({ cause: "combination", filter_id: null }) });
    expect(screen.queryByRole("button", { name: /hidden jobs/i })).not.toBeInTheDocument();
  });
});

describe("EmptyJobsExplanation, a never-matched search sharing the blame", () => {
  it("still says the search has never matched when the cause is a combination", () => {
    // The compound case: the rest of the corpus is excluded too, so `filter_id` is null and a check
    // on `filter_id === "search_id"` alone went silent — while `search_runs` and `search_ever_found`
    // were sitting in the response the whole time.
    setup({
      reason: reason({
        cause: "combination",
        filter_id: null,
        search_name: "Bay Area PM",
        search_location: "San Francisco Bay Area",
        search_runs: 3,
        search_ever_found: false,
      }),
    });
    expect(screen.getByText(/Bay Area PM has run 3 times and never returned a job/i)).toBeInTheDocument();
    expect(screen.queryByText(/removing any single one of them/i)).not.toBeInTheDocument();
  });

  it("does not override a more specific blame on a different filter", () => {
    // `posted_within` is blamed and widening it would reveal ten jobs. That is more actionable than
    // the search's history, so the one-click fix must not be buried.
    setup({
      reason: reason({
        cause: "filter",
        filter_id: "posted_within",
        filter_value: "24h",
        would_match: 10,
        search_name: "Bay Area PM",
        search_runs: 3,
        search_ever_found: false,
      }),
    });
    expect(screen.getByText(/date filter excluded everything/i)).toBeInTheDocument();
    expect(screen.queryByText(/never returned a job/i)).not.toBeInTheDocument();
  });

  it("stays quiet for a combination when the search HAS matched before", () => {
    setup({
      reason: reason({ cause: "combination", filter_id: null, search_runs: 9, search_ever_found: true }),
    });
    expect(screen.queryByText(/never returned a job/i)).not.toBeInTheDocument();
    expect(screen.getByText(/removing any single one of them still leaves nothing/i)).toBeInTheDocument();
  });
});

describe("EmptyJobsExplanation, names rather than identifiers", () => {
  it("names the saved search instead of printing its UUID", () => {
    // `filter_value` for `search_id` is `str(p.search_id)` on the server — correct there, one
    // definition per filter — but the response already carries `search_name` for the sentence.
    setup({
      reason: reason({
        cause: "filter",
        filter_id: "search_id",
        filter_value: "3f2a1b8c-7d4e-4f10-9b22-0a1c2d3e4f50",
        would_match: 6,
        search_name: "Bay Area PM",
        search_runs: 9,
        search_ever_found: true,
      }),
    });
    expect(screen.getByText(/saved search: Bay Area PM/)).toBeInTheDocument();
    expect(screen.queryByText(/3f2a1b8c/)).not.toBeInTheDocument();
  });

  it("names the taxonomy field instead of printing its id", () => {
    setup({
      reason: reason({
        cause: "filter",
        filter_id: "field",
        filter_value: "program-project-management",
        would_match: 4,
        field_name: "Program and Project Management",
      }),
    });
    expect(screen.getByText(/field: Program and Project Management/)).toBeInTheDocument();
    expect(screen.queryByText(/program-project-management/)).not.toBeInTheDocument();
  });

  it("falls back to the raw value when no name was sent", () => {
    setup({ reason: reason({ cause: "filter", filter_id: "sources", filter_value: "adzuna", would_match: 3 }) });
    expect(screen.getByText(/source: adzuna/)).toBeInTheDocument();
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
