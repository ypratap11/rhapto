import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { toast } from "sonner";
import { describe, expect, it, vi } from "vitest";
import { LocationTab } from "./LocationTab";

// Mutable per-test fixture — see BlocksTab.test.tsx's note on why a fixed shared object across
// every test would make this mock return the same thing regardless of what a test staged.
let answersData: Record<string, string> = {};

const putAnswers = vi.fn().mockResolvedValue({});
vi.mock("@/lib/api/queries", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/queries")>()),
  useAnswers: () => ({ data: answersData, isLoading: false, error: null, isPaused: false }),
  usePutAnswers: () => ({ mutateAsync: putAnswers, isPending: false }),
}));

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

describe("LocationTab", () => {
  it("renders existing location_home, location_preferred, and remote_ok values", () => {
    answersData = { location_home: "Austin, TX", location_preferred: "Austin, Dallas", remote_ok: "yes" };
    render(<LocationTab />);

    expect(screen.getByLabelText(/home location/i)).toHaveValue("Austin, TX");
    expect(screen.getByLabelText(/preferred areas/i)).toHaveValue("Austin, Dallas");
    expect(screen.getByRole("switch", { name: /open to remote/i })).toHaveAttribute("aria-checked", "true");
  });

  it("writes all three location keys on save, defaulting a never-set remote_ok to no", async () => {
    answersData = {};
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
    answersData = {
      location: "Remote, US",
      relocation: "no",
      onsite_preference: "hybrid",
      name: "Alex Doe",
      email: "alex@example.com",
    };
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
    answersData = {};
    render(<LocationTab />);
    const user = userEvent.setup({ delay: null });
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(toast.success).toHaveBeenCalledWith(expect.stringMatching(/re-score/i));
  });

  it("shows an error toast when the save fails", async () => {
    answersData = {};
    putAnswers.mockRejectedValueOnce(new Error("boom"));
    render(<LocationTab />);
    const user = userEvent.setup({ delay: null });
    await user.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(toast.error).toHaveBeenCalled());
  });
});
