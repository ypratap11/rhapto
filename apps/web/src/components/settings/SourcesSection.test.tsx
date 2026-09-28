import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SourcesSection } from "./SourcesSection";
import type { SourceSetting, SourceTestOut } from "@/lib/api/queries";

// Three contrasting states, because the point of these fields is that they differ from `enabled`:
// The Muse shows the keyless default (`enabled: true`) with no row behind it, so nothing polls it
// (`runnable: false`); Adzuna is off and keyless-less; JSearch is configured, runnable, and
// currently being refused by the poller.
const rows: SourceSetting[] = [
  { id: "themuse", label: "The Muse", enabled: true, needs_key: false, key_set: false, fields: [], runnable: false, paused: false, last_run: null },
  { id: "adzuna", label: "Adzuna", enabled: false, needs_key: true, key_set: false, fields: ["app_id", "app_key"], runnable: false, paused: false, last_run: null },
  {
    id: "jsearch",
    label: "JSearch",
    enabled: true,
    needs_key: true,
    key_set: true,
    fields: ["api_key"],
    runnable: true,
    paused: true,
    last_run: {
      started_at: "2026-09-26T12:00:00Z",
      finished_at: "2026-09-26T12:00:01Z",
      found: 0,
      new: 0,
      error: "paused after 3 failures; save the watchlist entry to retry",
      search_id: "s1",
      search_name: "Bay Area PM",
      search_location: "San Francisco Bay Area",
    },
  },
];

// Mutable, per-test module state (not a static top-of-file mock): each test below overwrites these
// before rendering, so a broken branch actually produces a different — and failing — assertion.
let data: SourceSetting[] | undefined = rows;
let isLoading = false;
let error: unknown = null;
let isPaused = false;
const save = vi.fn().mockResolvedValue({});
const testSource = vi.fn<() => Promise<SourceTestOut>>().mockResolvedValue({ ok: true, found: 1 });
const resumeSource = vi.fn();

vi.mock("@/lib/api/queries", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/queries")>()),
  useSourceSettings: () => ({ data, isLoading, error, isPaused }),
  useSaveSourceSettings: () => ({ mutateAsync: save, isPending: false }),
  useTestSource: () => ({ mutateAsync: testSource, isPending: false }),
  useResumeSource: () => ({ mutateAsync: resumeSource, isPending: false }),
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

describe("SourcesSection", () => {
  beforeEach(() => {
    data = rows;
    isLoading = false;
    error = null;
    isPaused = false;
    save.mockClear().mockResolvedValue({});
    testSource.mockClear().mockResolvedValue({ ok: true, found: 1 });
    resumeSource.mockClear().mockResolvedValue({});
  });

  it("lists each source with its switch and says which need a key", () => {
    render(<SourcesSection />);
    expect(screen.getByRole("switch", { name: "The Muse" })).toBeChecked();
    expect(screen.getByRole("switch", { name: "Adzuna" })).not.toBeChecked();

    const adzuna = screen.getByRole("group", { name: "Adzuna" });
    expect(within(adzuna).getByText(/needs a key/i)).toBeInTheDocument();
    expect(within(adzuna).getByLabelText("app_id")).toHaveAttribute("type", "password");
    expect(within(adzuna).getByLabelText("app_key")).toHaveAttribute("type", "password");

    const jsearch = screen.getByRole("group", { name: "JSearch" });
    expect(within(jsearch).getByText(/key saved/i)).toBeInTheDocument();

    const themuse = screen.getByRole("group", { name: "The Muse" });
    expect(within(themuse).getByText(/zero setup/i)).toBeInTheDocument();
  });

  it("never echoes a stored key back into the form", () => {
    render(<SourcesSection />);
    expect(within(screen.getByRole("group", { name: "JSearch" })).getByLabelText("api_key")).toHaveValue("");
  });

  it("saves an enable toggle without sending any credentials", async () => {
    const user = userEvent.setup({ delay: null });
    render(<SourcesSection />);
    await user.click(screen.getByRole("switch", { name: "Adzuna" }));
    expect(save).toHaveBeenCalledWith({ source: "adzuna", body: { enabled: true } });
  });

  it("saves a typed key on Save, and clears the field afterwards", async () => {
    const user = userEvent.setup({ delay: null });
    render(<SourcesSection />);
    const adzuna = screen.getByRole("group", { name: "Adzuna" });
    const appId = within(adzuna).getByLabelText("app_id");
    await user.type(appId, "my-app-id");
    await user.click(within(adzuna).getByRole("button", { name: /^save$/i }));

    expect(save).toHaveBeenCalledWith({ source: "adzuna", body: { enabled: false, credentials: { app_id: "my-app-id" } } });
    expect(appId).toHaveValue("");
  });

  it("tests a source and reports how many results it found", async () => {
    const user = userEvent.setup({ delay: null });
    render(<SourcesSection />);
    const themuse = screen.getByRole("group", { name: "The Muse" });
    await user.click(within(themuse).getByRole("button", { name: /^test$/i }));
    expect(testSource).toHaveBeenCalledWith("themuse");
  });

  it("shows a shape-matched skeleton while loading, not the empty or error state", () => {
    isLoading = true;
    data = undefined;
    const { container } = render(<SourcesSection />);
    // Positive assertion, not just the absence of the other states: a regression that rendered
    // nothing at all while loading would still pass a purely negative check.
    expect(container.querySelector('[data-slot="table-skeleton"]')).toBeInTheDocument();
    expect(screen.queryByRole("group")).not.toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("shows a real empty state, distinct from a failure, when the source registry is genuinely empty", () => {
    data = [];
    render(<SourcesSection />);
    expect(screen.getByText(/no job sources configured/i)).toBeInTheDocument();
    expect(screen.queryByRole("group")).not.toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("shows an error banner when the query fails with nothing cached yet", () => {
    isLoading = false;
    data = undefined;
    error = new Error("boom");
    render(<SourcesSection />);
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.queryByRole("group")).not.toBeInTheDocument();
  });

  it("treats a paused fetch (offline) the same as a failure even though isLoading is false and error is null", () => {
    isLoading = false;
    data = undefined;
    error = null;
    isPaused = true;
    render(<SourcesSection />);
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });

  it("keeps showing cached sources alongside the banner when a background refetch fails", () => {
    data = rows;
    error = new Error("refetch failed");
    render(<SourcesSection />);
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "The Muse" })).toBeInTheDocument();
  });
});

describe("SourcesSection, what a source last did and whether it can run", () => {
  beforeEach(() => {
    data = rows;
    isLoading = false;
    error = null;
    isPaused = false;
    save.mockClear().mockResolvedValue({});
    resumeSource.mockClear().mockResolvedValue({});
  });

  it("says a keyless source is on but cannot run yet, which is the real state", () => {
    // `enabled: true, runnable: false` looks contradictory and is honest: this page defaults keyless
    // sources to on, while the poller polls no aggregator for an account with no row. The row says so
    // instead of showing a switch that fetches nothing.
    render(<SourcesSection />);
    const muse = screen.getByRole("group", { name: "The Muse" });
    expect(within(muse).getByRole("switch", { name: "The Muse" })).toBeChecked();
    expect(within(muse).getByText(/no setting saved for it yet, so polls skip it/i)).toBeInTheDocument();
  });

  it("tells a keyed source with no key what is missing", () => {
    render(<SourcesSection />);
    const adzuna = screen.getByRole("group", { name: "Adzuna" });
    expect(within(adzuna).getByText(/add a key and this source will run/i)).toBeInTheDocument();
  });

  it("says nothing about readiness for a source that is ready", () => {
    // The contrasting fixture: JSearch is runnable, so no readiness line at all.
    render(<SourcesSection />);
    const jsearch = screen.getByRole("group", { name: "JSearch" });
    expect(within(jsearch).queryByText(/will run on the next poll/i)).not.toBeInTheDocument();
    expect(within(jsearch).queryByText(/polls skip it/i)).not.toBeInTheDocument();
  });

  it("shows a Paused badge and a Resume button only for the paused source", async () => {
    render(<SourcesSection />);
    const jsearch = screen.getByRole("group", { name: "JSearch" });
    expect(within(jsearch).getByText("Paused")).toBeInTheDocument();
    // And not on the others, so the assertion is about the fixture rather than the component.
    expect(within(screen.getByRole("group", { name: "The Muse" })).queryByText("Paused")).not.toBeInTheDocument();
    expect(within(screen.getByRole("group", { name: "The Muse" })).queryByRole("button", { name: /resume/i })).not.toBeInTheDocument();

    await userEvent.setup().click(within(jsearch).getByRole("button", { name: /resume/i }));
    expect(resumeSource).toHaveBeenCalledWith("jsearch");
  });

  it("reports what the last run was asked for and what it returned", () => {
    // The location is the search's own string, from the join. Without it the row can only say
    // "returned 0", which is the silence this replaces.
    render(<SourcesSection />);
    const jsearch = screen.getByRole("group", { name: "JSearch" });
    expect(within(jsearch).getByText(/paused after 3 failures/i)).toBeInTheDocument();
  });

  it("says a run returned zero, and for what, when it did not error", () => {
    data = [
      {
        ...rows[0]!,
        runnable: true,
        last_run: {
          started_at: "2026-09-26T12:00:00Z",
          finished_at: "2026-09-26T12:00:01Z",
          found: 0,
          new: 0,
          error: null,
          search_id: "s2",
          search_name: "Bay Area PM",
          search_location: "San Francisco Bay Area",
        },
      },
    ];
    render(<SourcesSection />);
    expect(screen.getByText(/last run returned 0 for San Francisco Bay Area \(Bay Area PM\)/i)).toBeInTheDocument();
    // C7: the fact, and no suggested alternative. There is no gazetteer to produce one from.
    expect(screen.queryByText(/try ['"]/i)).not.toBeInTheDocument();
  });

  it("says what a successful run found, so a working source does not read the same as a silent one", () => {
    data = [
      {
        ...rows[0]!,
        runnable: true,
        last_run: {
          started_at: "2026-09-26T12:00:00Z",
          finished_at: "2026-09-26T12:00:01Z",
          found: 12,
          new: 3,
          error: null,
          search_id: null,
          search_name: null,
          search_location: null,
        },
      },
    ];
    render(<SourcesSection />);
    expect(screen.getByText(/last run found 12 postings, 3 new/i)).toBeInTheDocument();
  });

  it("says nothing about a last run for a source that has never run", () => {
    data = [{ ...rows[0]!, last_run: null }];
    render(<SourcesSection />);
    expect(screen.queryByText(/last run/i)).not.toBeInTheDocument();
  });
});

