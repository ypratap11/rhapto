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
