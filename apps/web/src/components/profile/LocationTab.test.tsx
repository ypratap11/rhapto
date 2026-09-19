import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { toast } from "sonner";
import { describe, expect, it, vi } from "vitest";
import { LocationTab } from "./LocationTab";

type AnswersState = { data: Record<string, string> | undefined; isLoading: boolean; error: unknown; isPaused: boolean };

// Mutable per-test fixture, not a fixed shared object — see BlocksTab.test.tsx's note on why a
// mock has to vary with each test's staging to be worth anything. `answersState` controls all four
// query-result fields directly so a test can stage the paused/unloaded case exactly, not just the
// "loaded with some data" case a flat `Record<string,string>` fixture could only express.
let answersState: AnswersState = { data: {}, isLoading: false, error: null, isPaused: false };
function setAnswers(data: Record<string, string>) {
  answersState = { data, isLoading: false, error: null, isPaused: false };
}

const putAnswers = vi.fn().mockResolvedValue({});
vi.mock("@/lib/api/queries", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/queries")>()),
  useAnswers: () => answersState,
  usePutAnswers: () => ({ mutateAsync: putAnswers, isPending: false }),
}));

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

describe("LocationTab", () => {
  it("renders existing location_home, location_preferred, and remote_ok values", () => {
    setAnswers({ location_home: "Austin, TX", location_preferred: "Austin, Dallas", remote_ok: "yes" });
    render(<LocationTab />);

    expect(screen.getByLabelText(/home location/i)).toHaveValue("Austin, TX");
    expect(screen.getByLabelText(/preferred areas/i)).toHaveValue("Austin, Dallas");
    expect(screen.getByRole("switch", { name: /open to remote/i })).toHaveAttribute("aria-checked", "true");
  });

  it("writes all three location keys on save, defaulting a never-set remote_ok to no", async () => {
    setAnswers({});
    putAnswers.mockClear();
    render(<LocationTab />);
    const user = userEvent.setup({ delay: null });

    await user.type(screen.getByLabelText(/home location/i), "Austin, TX");
    await user.type(screen.getByLabelText(/preferred areas/i), "Austin, Dallas");
    await user.click(screen.getByRole("switch", { name: /open to remote/i }));
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(putAnswers).toHaveBeenCalledWith(
      expect.objectContaining({ location_home: "Austin, TX", location_preferred: "Austin, Dallas", remote_ok: "yes" }),
    );
  });

  it("preserves every other answer key untouched (location, relocation, onsite_preference, ...) when saving", async () => {
    setAnswers({
      location: "Remote, US",
      relocation: "no",
      onsite_preference: "hybrid",
      name: "Alex Doe",
      email: "alex@example.com",
    });
    putAnswers.mockClear();
    render(<LocationTab />);
    const user = userEvent.setup({ delay: null });

    await user.type(screen.getByLabelText(/home location/i), "Denver, CO");
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(putAnswers).toHaveBeenCalledWith(
      expect.objectContaining({
        location: "Remote, US",
        relocation: "no",
        onsite_preference: "hybrid",
        name: "Alex Doe",
        email: "alex@example.com",
        location_home: "Denver, CO",
      }),
    );
  });

  it("shows a toast noting the queue re-scores by location tier", async () => {
    setAnswers({});
    render(<LocationTab />);
    const user = userEvent.setup({ delay: null });
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(toast.success).toHaveBeenCalledWith(expect.stringMatching(/re-score/i));
  });

  it("shows an error toast when the save fails", async () => {
    setAnswers({});
    putAnswers.mockRejectedValueOnce(new Error("boom"));
    render(<LocationTab />);
    const user = userEvent.setup({ delay: null });
    await user.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(toast.error).toHaveBeenCalled());
  });

  it("blocks Save entirely when answers are paused and were never loaded (unreachable API) — CRITICAL", async () => {
    // TanStack's networkMode: "online" parks an unreachable query at fetchStatus "paused":
    // isLoading is false, error is null, and data is undefined — the same shape a settled error's
    // "nothing cached" case has, and indistinguishable from "genuinely empty" by isLoading/error
    // alone. If LocationTab fell back to `initial = {}` here, an unaware Save would PUT
    // `{location_home:"", location_preferred:"", remote_ok:"no"}` and wipe every other answer key.
    putAnswers.mockClear();
    answersState = { data: undefined, isLoading: false, error: null, isPaused: true };
    render(<LocationTab />);

    // Asserting only that some banner/text renders would pass even if a working Save button also
    // rendered underneath it — the mutation itself must be unreachable, so assert there is no Save
    // control to click, and that no amount of the page's own buttons issues a PUT.
    expect(screen.queryByRole("button", { name: "Save" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/home location/i)).not.toBeInTheDocument();
    expect(putAnswers).not.toHaveBeenCalled();
  });

  it("shows a loading skeleton, not the paused/error state, while the first fetch is in flight", () => {
    answersState = { data: undefined, isLoading: true, error: null, isPaused: false };
    render(<LocationTab />);
    expect(screen.queryByRole("button", { name: "Save" })).not.toBeInTheDocument();
    expect(screen.queryByText(/can.?t reach/i)).not.toBeInTheDocument();
  });

  it("keeps editing enabled with a stale-data note when a background refetch fails but cached data exists", () => {
    answersState = { data: { location_home: "Austin, TX" }, isLoading: false, error: null, isPaused: true };
    render(<LocationTab />);
    expect(screen.getByLabelText(/home location/i)).toHaveValue("Austin, TX");
    expect(screen.getByRole("button", { name: "Save" })).toBeInTheDocument();
    expect(screen.getByText(/last saved location preferences/i)).toBeInTheDocument();
  });
});
