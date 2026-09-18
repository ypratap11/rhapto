import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { JobOut, PackageSummary } from "@/lib/api/queries";
import { markApplyOpened } from "@/lib/apply-prompt";
import { DidYouApplyPrompt } from "./DidYouApplyPrompt";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));

const markApplied = vi.fn().mockResolvedValue(undefined);
const archive = vi.fn().mockResolvedValue({});
const hide = vi.fn().mockResolvedValue({});
const unhide = vi.fn().mockResolvedValue({});
vi.mock("@/lib/api/queries", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/queries")>()),
  useMarkApplied: () => ({ markApplied, isPending: false }),
  useArchivePackage: () => ({ mutateAsync: archive, isPending: false }),
  useHideJob: () => ({ mutateAsync: hide, isPending: false }),
  // Not in the brief's test snippet, but required: DidYouApplyPrompt calls useUnhideJob
  // unconditionally (Rules of Hooks — it is wired into the Skip toast's Undo action), and the
  // real hook needs a QueryClientProvider this test never sets up. Same treatment
  // NotInterestedButton.test.tsx gives useHideJob/useUnhideJob for the same reason.
  useUnhideJob: () => ({ mutateAsync: unhide, isPending: false }),
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const job = { id: "j1", company: "ExampleCo", title: "TPM" } as JobOut;
const pkg = { id: "p1", version: 2, status: "ready", mode: "tune", created_at: "2026-09-13T00:00:00Z" } as PackageSummary;

function show() {
  markApplyOpened("j1");
  const view = render(<DidYouApplyPrompt job={job} pkg={pkg} />);
  // Focus is a native window event, not a React-managed one, so the re-render it triggers (via
  // useApplyPrompt's useSyncExternalStore) needs an explicit act() to flush before the assertions
  // below query synchronously — the first test gets away without it only because findByText polls.
  act(() => {
    window.dispatchEvent(new Event("focus"));
  });
  return view;
}

describe("DidYouApplyPrompt", () => {
  it("asks once the tab comes back and records an application on Yes", async () => {
    const user = userEvent.setup({ delay: null });
    show();
    expect(await screen.findByText(/did you apply\?/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Yes" }));
    expect(markApplied).toHaveBeenCalledWith({ id: "j1" }, "p1", null);
  });

  it("keeps the resume ready on Not yet", async () => {
    const user = userEvent.setup({ delay: null });
    show();
    await user.click(screen.getByRole("button", { name: /not yet/i }));
    expect(markApplied).not.toHaveBeenCalled();
    expect(screen.queryByText(/did you apply\?/i)).toBeNull();
  });

  it("archives the package and hides the job on Skip", async () => {
    const user = userEvent.setup({ delay: null });
    show();
    await user.click(screen.getByRole("button", { name: "Skip" }));
    expect(archive).toHaveBeenCalledWith("p1");
    expect(hide).toHaveBeenCalledWith("j1");
  });
});
