import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SavedSearchesSection } from "./SavedSearchesSection";
import type { SearchOut } from "@/lib/api/queries";

const searches: SearchOut[] = [
  {
    id: "s1",
    name: "Staff engineer",
    keywords: ["staff", "engineer"],
    location: "Remote",
    remote: "only",
    active: true,
    derived_from_track_id: null,
    new_count: 2,
    created_at: "2026-09-01T00:00:00Z",
    last_viewed_at: null,
    // Has polled and has found postings before: today's zero is "nothing new".
    runs: 12,
    ever_found: true,
    last_run_at: "2026-09-26T00:00:00Z",
  },
  {
    id: "s2",
    name: "From backend track",
    keywords: [],
    location: null,
    remote: "include",
    active: true,
    derived_from_track_id: "track-1",
    new_count: 0,
    created_at: "2026-09-02T00:00:00Z",
    last_viewed_at: null,
    // Has polled three times and never found a posting -- spec section 8's own sentence.
    runs: 3,
    ever_found: false,
    last_run_at: "2026-09-26T00:00:00Z",
  },
];

// Mutable per-test state, not a static mock: the four-state tests below each stage a different
// shape and would fail if the component collapsed any two of them together.
let data: SearchOut[] | undefined = searches;
let isLoading = false;
let error: unknown = null;
let isPaused = false;
const update = vi.fn().mockResolvedValue(searches[0]);
const remove = vi.fn().mockResolvedValue(undefined);

vi.mock("@/lib/api/queries", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/queries")>()),
  useSavedSearches: () => ({ data, isLoading, error, isPaused }),
  useUpdateSavedSearch: () => ({ mutateAsync: update, isPending: false }),
  useDeleteSavedSearch: () => ({ mutateAsync: remove, isPending: false }),
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

describe("SavedSearchesSection", () => {
  beforeEach(() => {
    data = searches;
    isLoading = false;
    error = null;
    isPaused = false;
    update.mockClear().mockResolvedValue(searches[0]);
    remove.mockClear().mockResolvedValue(undefined);
  });

  it("lists one row per saved search with its keywords, location and remote setting", () => {
    render(<SavedSearchesSection />);
    const row = screen.getByText("Staff engineer").closest("li");
    expect(row).not.toBeNull();
    expect(row).toHaveTextContent("staff, engineer");
    expect(row).toHaveTextContent("Remote");
    expect(row).toHaveTextContent(/remote only/i);
  });

  it("badges a search derived from a track, and not one the user created directly", () => {
    render(<SavedSearchesSection />);
    const derived = screen.getByText("From backend track").closest("li");
    const direct = screen.getByText("Staff engineer").closest("li");
    expect(derived).not.toBeNull();
    expect(within(derived as HTMLElement).getByText("from a track")).toBeInTheDocument();
    expect(within(direct as HTMLElement).queryByText("from a track")).not.toBeInTheDocument();
  });

  it("pauses a search by writing active: false", async () => {
    const user = userEvent.setup({ delay: null });
    render(<SavedSearchesSection />);
    const row = screen.getByText("Staff engineer").closest("li") as HTMLElement;
    await user.click(within(row).getByRole("switch"));
    expect(update).toHaveBeenCalledWith({ id: "s1", body: expect.objectContaining({ active: false }) });
  });

  it("deletes a search only after the AlertDialog action is confirmed, and closes the dialog itself", async () => {
    const user = userEvent.setup({ delay: null });
    render(<SavedSearchesSection />);
    const row = screen.getByText("Staff engineer").closest("li") as HTMLElement;
    await user.click(within(row).getByRole("button", { name: /delete/i }));

    const dialog = await screen.findByRole("alertdialog");
    expect(remove).not.toHaveBeenCalled();
    await user.click(within(dialog).getByRole("button", { name: /^delete$/i }));

    expect(remove).toHaveBeenCalledWith("s1");
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  });

  it("edits a search in a Sheet and saves the new name", async () => {
    const user = userEvent.setup({ delay: null });
    render(<SavedSearchesSection />);
    const row = screen.getByText("Staff engineer").closest("li") as HTMLElement;
    await user.click(within(row).getByRole("button", { name: /edit/i }));

    const nameInput = screen.getByLabelText(/name/i);
    expect(nameInput).toHaveValue("Staff engineer");
    await user.clear(nameInput);
    await user.type(nameInput, "Principal engineer");
    await user.click(screen.getByRole("button", { name: /^save$/i }));

    expect(update).toHaveBeenCalledWith({ id: "s1", body: expect.objectContaining({ name: "Principal engineer" }) });
  });

  it("shows a shape-matched skeleton while loading, not the empty state", () => {
    isLoading = true;
    data = undefined;
    const { container } = render(<SavedSearchesSection />);
    // Positive assertion, not just the absence of the other states: a regression that rendered
    // nothing at all while loading would still pass a purely negative check.
    expect(container.querySelector('[data-slot="table-skeleton"]')).toBeInTheDocument();
    expect(screen.queryByText(/no saved searches yet/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("shows a real empty state distinct from a failure when there are genuinely no saved searches", () => {
    data = [];
    render(<SavedSearchesSection />);
    expect(screen.getByText(/no saved searches yet/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /jobs/i })).toHaveAttribute("href", "/jobs");
  });

  it("shows an error banner when nothing has loaded yet", () => {
    data = undefined;
    error = new Error("boom");
    render(<SavedSearchesSection />);
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.queryByText(/no saved searches yet/i)).not.toBeInTheDocument();
  });

  it("treats a paused fetch as a failure even though isLoading is false and error is null", () => {
    data = undefined;
    isPaused = true;
    render(<SavedSearchesSection />);
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });

  it("keeps showing cached rows alongside the banner when a background refetch fails", () => {
    data = searches;
    error = new Error("refetch failed");
    render(<SavedSearchesSection />);
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByText("Staff engineer")).toBeInTheDocument();
  });
});

describe("SavedSearchesSection, a search that has never matched", () => {
  beforeEach(() => {
    data = searches;
    isLoading = false;
    error = null;
    isPaused = false;
  });

  it("marks the search that has polled and never returned a job, and not the one that has", () => {
    // Both rows show no new-count. The distinction has to come from the run history, or the two are
    // indistinguishable -- which is exactly how a misconfigured search hid for weeks.
    render(<SavedSearchesSection />);
    const never = screen.getByText("From backend track").closest("li")!;
    const found = screen.getByText("Staff engineer").closest("li")!;
    expect(within(never).getByText("Never matched")).toBeInTheDocument();
    expect(within(never).getByText(/has run 3 times and never returned a job/i)).toBeInTheDocument();
    expect(within(found).queryByText("Never matched")).not.toBeInTheDocument();
    expect(within(found).getByText(/has found jobs before/i)).toBeInTheDocument();
  });

  it("says a search has not run yet rather than that it found nothing", () => {
    data = [{ ...searches[0]!, runs: 0, ever_found: false, last_run_at: null }];
    render(<SavedSearchesSection />);
    expect(screen.getByText(/has not run yet/i)).toBeInTheDocument();
    expect(screen.queryByText(/never returned a job/i)).not.toBeInTheDocument();
    expect(screen.queryByText("Never matched")).not.toBeInTheDocument();
  });

  it("says once, not 1 times", () => {
    data = [{ ...searches[0]!, runs: 1, ever_found: false }];
    render(<SavedSearchesSection />);
    expect(screen.getByText(/has run once and never returned a job/i)).toBeInTheDocument();
  });

  it("asserts no cause for the zero and suggests no other location", () => {
    // Condition C7. `poll_runs` records `found = 0, error = NULL` whether the location was
    // unrecognised, the keywords too narrow, the source uncovered or the market empty.
    const { container } = render(<SavedSearchesSection />);
    const text = container.textContent ?? "";
    expect(text).not.toMatch(/may not be recognised|not recognised|unrecognised/i);
    expect(text).not.toMatch(/try ['"]/i);
  });
});

