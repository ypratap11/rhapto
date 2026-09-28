import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { DashboardChecklist } from "@/lib/api/queries";
import { ProfileChecklist } from "./ProfileChecklist";

/** A fully unset setup: this is what a stranger's first dashboard actually looks like. */
const base: DashboardChecklist = {
  resume_template: true,
  contact_answers: false,
  tracks: true,
  blocks_verified: false,
  guardrails: true,
  location_preferences: false,
  verified_blocks: 18,
  total_blocks: 23,
  llm_key: false,
  llm_key_source: "none",
  trial_runs_left: null,
  job_sources: false,
  usable_sources: 0,
  saved_searches: false,
  active_searches: 0,
  jobs_found: false,
  dateless_blocks: 0,
};

const checklist = base;

function row(label: string): HTMLElement {
  const heading = screen.getByText(label);
  const item = heading.closest("li");
  if (!item) throw new Error(`no row for ${label}`);
  return item;
}

describe("ProfileChecklist", () => {
  it("shows all eleven rows, the verified count, and an Edit deep link per row", () => {
    render(<ProfileChecklist checklist={checklist} />);
    const rows = screen.getAllByRole("listitem");
    expect(rows).toHaveLength(11);
    expect(screen.getByText("18 of 23 verified")).toBeInTheDocument();
    expect(within(rows[0]!).getByRole("link", { name: /edit/i })).toHaveAttribute("href", "/profile?card=resume-template");
    expect(within(rows[1]!).getByRole("link", { name: /edit/i })).toHaveAttribute("href", "/profile?card=answers");
    expect(within(rows[5]!).getByRole("link", { name: /edit/i })).toHaveAttribute("href", "/profile?card=location");
  });

  it("deep-links every setup row to the place that fixes it", () => {
    render(<ProfileChecklist checklist={checklist} />);
    // The point of these rows is that an unmet one is one click from its fix. A row that says
    // "no source can run yet" and links nowhere useful is the empty state it replaced.
    expect(within(row("LLM key")).getByRole("link", { name: /edit/i })).toHaveAttribute("href", "/settings");
    expect(within(row("Job sources")).getByRole("link", { name: /edit/i })).toHaveAttribute("href", "/settings");
    expect(within(row("Saved searches")).getByRole("link", { name: /edit/i })).toHaveAttribute("href", "/settings");
    expect(within(row("Jobs found")).getByRole("link", { name: /edit/i })).toHaveAttribute("href", "/jobs");
    expect(within(row("Block dates")).getByRole("link", { name: /edit/i })).toHaveAttribute("href", "/profile?card=blocks");
  });

  it("marks done and not-done rows for a screen reader", () => {
    render(<ProfileChecklist checklist={checklist} />);
    expect(screen.getAllByRole("listitem")[0]).toHaveAttribute("data-done", "true");
    expect(screen.getAllByRole("listitem")[1]).toHaveAttribute("data-done", "false");
  });

  // --- the LLM row's four states. Rendered from four different fixtures, so no assertion can pass
  // on a string that is simply always there.

  it("says whose key is paying, not just whether one exists", () => {
    const { unmount } = render(<ProfileChecklist checklist={{ ...base, llm_key: true, llm_key_source: "settings" }} />);
    expect(row("LLM key")).toHaveAttribute("data-done", "true");
    expect(within(row("LLM key")).getByText("Your own key")).toBeInTheDocument();
    unmount();

    render(<ProfileChecklist checklist={{ ...base, llm_key: true, llm_key_source: "env" }} />);
    expect(row("LLM key")).toHaveAttribute("data-done", "true");
    expect(within(row("LLM key")).getByText("This instance's key")).toBeInTheDocument();
  });

  it("counts down the free runs while any remain", () => {
    const { unmount } = render(
      <ProfileChecklist checklist={{ ...base, llm_key: true, llm_key_source: "trial", trial_runs_left: 3 }} />,
    );
    expect(row("LLM key")).toHaveAttribute("data-done", "true");
    expect(within(row("LLM key")).getByText(/3 free runs left/i)).toBeInTheDocument();
    unmount();

    // Singular, because "1 free runs left" is the kind of detail that makes a product feel unmade.
    render(<ProfileChecklist checklist={{ ...base, llm_key: true, llm_key_source: "trial", trial_runs_left: 1 }} />);
    expect(within(row("LLM key")).getByText(/1 free run left/i)).toBeInTheDocument();
  });

  it("flips the LLM row to not-done with a next action once the free runs are gone", () => {
    // The state the whole four-way split exists for: a key IS configured, and the user is blocked.
    // "Configured" would be true and useless; this row has to hand them the next action.
    render(<ProfileChecklist checklist={{ ...base, llm_key: false, llm_key_source: "trial", trial_runs_left: 0 }} />);
    expect(row("LLM key")).toHaveAttribute("data-done", "false");
    expect(within(row("LLM key")).getByText(/free runs used/i)).toBeInTheDocument();
    expect(within(row("LLM key")).getByText(/add your own key/i)).toBeInTheDocument();
  });

  it("asks for a key when there is none anywhere", () => {
    render(<ProfileChecklist checklist={base} />);
    expect(row("LLM key")).toHaveAttribute("data-done", "false");
    expect(within(row("LLM key")).getByText("Add a provider key")).toBeInTheDocument();
  });

  // --- the other four setup rows, each with both states

  it("says no source can run yet, then how many are ready", () => {
    const { unmount } = render(<ProfileChecklist checklist={base} />);
    expect(row("Job sources")).toHaveAttribute("data-done", "false");
    expect(within(row("Job sources")).getByText("No source can run yet")).toBeInTheDocument();
    unmount();

    render(<ProfileChecklist checklist={{ ...base, job_sources: true, usable_sources: 4 }} />);
    expect(row("Job sources")).toHaveAttribute("data-done", "true");
    expect(within(row("Job sources")).getByText("4 sources ready")).toBeInTheDocument();
  });

  it("counts only the active saved searches", () => {
    const { unmount } = render(<ProfileChecklist checklist={base} />);
    expect(within(row("Saved searches")).getByText(/save a search/i)).toBeInTheDocument();
    unmount();

    render(<ProfileChecklist checklist={{ ...base, saved_searches: true, active_searches: 2 }} />);
    expect(row("Saved searches")).toHaveAttribute("data-done", "true");
    expect(within(row("Saved searches")).getByText("2 active")).toBeInTheDocument();
  });

  it("tells a stranger with no jobs to run a poll", () => {
    const { unmount } = render(<ProfileChecklist checklist={base} />);
    expect(row("Jobs found")).toHaveAttribute("data-done", "false");
    expect(within(row("Jobs found")).getByText(/run a poll/i)).toBeInTheDocument();
    unmount();

    render(<ProfileChecklist checklist={{ ...base, jobs_found: true }} />);
    expect(row("Jobs found")).toHaveAttribute("data-done", "true");
    expect(within(row("Jobs found")).getByText(/jobs are arriving/i)).toBeInTheDocument();
  });

  it("counts the blocks that need a period and follows the number it was given", () => {
    const { unmount } = render(<ProfileChecklist checklist={{ ...base, dateless_blocks: 3 }} />);
    expect(row("Block dates")).toHaveAttribute("data-done", "false");
    expect(within(row("Block dates")).getByText("3 need a period")).toBeInTheDocument();
    unmount();

    // A second, different count, so the assertion cannot be satisfied by a literal.
    const second = render(<ProfileChecklist checklist={{ ...base, dateless_blocks: 7 }} />);
    expect(within(row("Block dates")).getByText("7 need a period")).toBeInTheDocument();
    second.unmount();

    render(<ProfileChecklist checklist={base} />);
    expect(row("Block dates")).toHaveAttribute("data-done", "true");
    expect(within(row("Block dates")).getByText(/every block has a period/i)).toBeInTheDocument();
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

  it("renders as many skeleton rows as there are real rows", () => {
    // Otherwise the page jumps on every load, and a hard-coded count stops matching the moment a
    // row is added — which is exactly what happened when five rows were added to a `length: 6`.
    const skeleton = render(<ProfileChecklist checklist={null} loading />);
    const placeholders = skeleton.container.querySelectorAll("li");
    skeleton.unmount();
    render(<ProfileChecklist checklist={checklist} />);
    expect(placeholders).toHaveLength(screen.getAllByRole("listitem").length);
  });

  it("renders nothing when settled with no checklist to show (not loading, no data)", () => {
    const { container } = render(<ProfileChecklist checklist={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("says the checklist failed to load instead of silently rendering nothing", () => {
    // Once a failed dashboard call settles, loading goes false with checklist still null — the
    // same shape a genuinely-nothing-to-show case has. `error` must produce a visible state, not
    // fall through to the silent `!checklist` branch above.
    render(<ProfileChecklist checklist={null} error />);
    expect(screen.getByTestId("checklist-error")).toBeInTheDocument();
    expect(screen.getByText(/couldn.t load/i)).toBeInTheDocument();
    expect(screen.queryAllByRole("listitem")).toHaveLength(0);
  });
});
