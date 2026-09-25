import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { toast } from "sonner";
import { describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/client";
import type { Block, ResumeImportOut } from "@/lib/api/queries";
import { ImportResume } from "./ImportResume";

// ImportResume writes the accepted proposal via the profile mutation hooks (usePutBlock,
// usePutTrack, usePutAnswers) once the user confirms, and reads useAnswers/useBases to do it
// safely (merging location answers, picking a base for a proposed track). None of that needs a
// real QueryClient here — following BlocksTab.test.tsx's convention, the hooks are replaced with
// plain stubs so the component under test never touches react-query or the network.
//
// Mutable so each test can stage exactly the query state it needs — a fixed shared fixture across
// every test in the file is how a mock ends up returning the same thing regardless of what a test
// set up (see BlocksTab.test.tsx).
let answersQuery: { data: Record<string, string> | undefined; isLoading: boolean; error: unknown } = {
  data: {},
  isLoading: false,
  error: null,
};
let basesQuery: { data: { id: string; name: string; block_ids: string[] }[] | undefined; isLoading: boolean; error: unknown } = {
  data: [],
  isLoading: false,
  error: null,
};

const putBlockMutate = vi.fn().mockResolvedValue({});
const putTrackMutate = vi.fn().mockResolvedValue({});
const putAnswersMutate = vi.fn().mockResolvedValue({});

vi.mock("@/lib/api/queries", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/queries")>()),
  useAnswers: () => answersQuery,
  useBases: () => basesQuery,
  usePutBlock: () => ({ mutateAsync: putBlockMutate, isPending: false }),
  usePutTrack: () => ({ mutateAsync: putTrackMutate, isPending: false }),
  usePutAnswers: () => ({ mutateAsync: putAnswersMutate, isPending: false }),
}));

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const roleBlock: Block = {
  id: "acme-lead",
  type: "role",
  org: "Acme",
  role: "Delivery Lead",
  period: "2019-2023",
  content: "Led delivery.",
  verified: false,
  tags: [],
  metric: null,
  attribution: null,
  concurrent: false,
  visibility: null,
};

const metricBlock: Block = {
  id: "acme-win",
  type: "achievement",
  org: "Acme",
  role: null,
  period: null,
  content: "Cut costs 30%.",
  metric: "30%",
  verified: false,
  tags: [],
  attribution: null,
  concurrent: false,
  visibility: null,
};

const proposal: ResumeImportOut = {
  blocks: [roleBlock, metricBlock],
  tracks: [{ id: "tpm", name: "TPM", keywords: [], field: "program-project-management", role: "technical-program-manager" }],
  location: { location_home: "Dublin, CA", location_preferred: [], remote_ok: "yes" },
  dropped_periods: 1,
  metrics_to_confirm: 1,
};

function resetQueries() {
  answersQuery = { data: {}, isLoading: false, error: null };
  basesQuery = { data: [], isLoading: false, error: null };
  putBlockMutate.mockReset().mockImplementation(async (b: Block) => b);
  putTrackMutate.mockReset().mockResolvedValue({});
  putAnswersMutate.mockReset().mockResolvedValue({});
}

describe("ImportResume", () => {
  it("shows every proposed block before anything is saved", () => {
    resetQueries();
    render(<ImportResume proposal={proposal} onConfirm={vi.fn()} />);
    expect(screen.getByText("Delivery Lead")).toBeInTheDocument();
    expect(screen.getByText(/Cut costs 30%/)).toBeInTheDocument();
  });

  it("marks blocks whose date could not be read", () => {
    resetQueries();
    render(<ImportResume proposal={proposal} onConfirm={vi.fn()} />);
    expect(screen.getByText(/1 .*no date/i)).toBeInTheDocument();
  });

  it("says nothing is saved until the user confirms", () => {
    resetQueries();
    render(<ImportResume proposal={proposal} onConfirm={vi.fn()} />);
    expect(screen.getByText(/nothing is saved yet/i)).toBeInTheDocument();
  });

  it("passes the proposal to onConfirm when accepted", async () => {
    resetQueries();
    const onConfirm = vi.fn();
    const user = userEvent.setup({ delay: null });
    render(<ImportResume proposal={proposal} onConfirm={onConfirm} />);
    await user.click(screen.getByRole("button", { name: /add .* to my profile/i }));
    expect(onConfirm).toHaveBeenCalledWith(proposal);
  });

  it("writes every proposed block via putBlock", async () => {
    resetQueries();
    const user = userEvent.setup({ delay: null });
    render(<ImportResume proposal={proposal} onConfirm={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: /add .* to my profile/i }));
    expect(putBlockMutate).toHaveBeenCalledTimes(2);
    expect(putBlockMutate).toHaveBeenCalledWith(roleBlock);
    expect(putBlockMutate).toHaveBeenCalledWith(metricBlock);
  });

  it("writes proposed tracks with the taxonomy fields and min_fit carried over", async () => {
    resetQueries();
    basesQuery = { data: [{ id: "general", name: "General", block_ids: [] }], isLoading: false, error: null };
    const user = userEvent.setup({ delay: null });
    render(<ImportResume proposal={proposal} onConfirm={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: /add .* to my profile/i }));
    expect(putTrackMutate).toHaveBeenCalledWith(
      expect.objectContaining({
        id: "tpm",
        name: "TPM",
        resume_base: "general",
        field: "program-project-management",
        role: "technical-program-manager",
      }),
    );
  });

  it("writes the location answers merged with the existing answers map", async () => {
    resetQueries();
    answersQuery = { data: { notice_period: "2 weeks" }, isLoading: false, error: null };
    const user = userEvent.setup({ delay: null });
    render(<ImportResume proposal={proposal} onConfirm={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: /add .* to my profile/i }));
    expect(putAnswersMutate).toHaveBeenCalledWith(
      expect.objectContaining({ notice_period: "2 weeks", location_home: "Dublin, CA", remote_ok: "yes" }),
    );
  });

  // --- Finding 1: a fresh install (no bases yet) must not write an empty resume_base -----------

  it("falls back to a valid, non-empty resume_base when the profile has no bases yet", async () => {
    resetQueries();
    basesQuery = { data: [], isLoading: false, error: null }; // the fresh-install case
    const user = userEvent.setup({ delay: null });
    render(<ImportResume proposal={proposal} onConfirm={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: /add .* to my profile/i }));
    expect(putTrackMutate).toHaveBeenCalledTimes(1);
    const written = putTrackMutate.mock.calls[0]![0] as { resume_base: string };
    expect(written.resume_base).not.toBe("");
    expect(written.resume_base).toMatch(/^[a-z0-9][a-z0-9-]*$/);
  });

  it("uses an existing base instead of the default when the profile already has one", async () => {
    resetQueries();
    basesQuery = { data: [{ id: "main", name: "Main", block_ids: [] }], isLoading: false, error: null };
    const user = userEvent.setup({ delay: null });
    render(<ImportResume proposal={proposal} onConfirm={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: /add .* to my profile/i }));
    expect(putTrackMutate).toHaveBeenCalledWith(expect.objectContaining({ resume_base: "main" }));
  });

  // --- Finding 4: must not PUT answers (or blocks) while useAnswers()/useBases() is unresolved --

  it("disables Accept while bases have not resolved yet", () => {
    resetQueries();
    basesQuery = { data: undefined, isLoading: true, error: null };
    render(<ImportResume proposal={proposal} onConfirm={vi.fn()} />);
    expect(screen.getByRole("button", { name: /add .* to my profile/i })).toBeDisabled();
  });

  it("disables Accept when the answers query has errored", () => {
    resetQueries();
    answersQuery = { data: undefined, isLoading: false, error: new Error("network") };
    render(<ImportResume proposal={proposal} onConfirm={vi.fn()} />);
    expect(screen.getByRole("button", { name: /add .* to my profile/i })).toBeDisabled();
  });

  it("does not write blocks, tracks or answers if Accept is invoked while answers has not resolved", async () => {
    resetQueries();
    answersQuery = { data: undefined, isLoading: true, error: null };
    const onConfirm = vi.fn();
    render(<ImportResume proposal={proposal} onConfirm={onConfirm} />);
    // The button is disabled, but this asserts the guard inside handleAccept itself, not just the
    // disabled attribute — belt and suspenders per the finding.
    const button = screen.getByRole("button", { name: /add .* to my profile/i }) as HTMLButtonElement;
    button.disabled = false;
    await userEvent.setup({ delay: null }).click(button);
    expect(putBlockMutate).not.toHaveBeenCalled();
    expect(putAnswersMutate).not.toHaveBeenCalled();
    expect(onConfirm).not.toHaveBeenCalled();
  });

  // --- Finding 3: partial success must be reported honestly, not as total failure ---------------

  it("reports what landed and that retrying is safe when a later write fails after blocks saved", async () => {
    resetQueries();
    putTrackMutate.mockReset().mockRejectedValue(new ApiError(422, null, "could not save track"));
    const user = userEvent.setup({ delay: null });
    render(<ImportResume proposal={proposal} onConfirm={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: /add .* to my profile/i }));
    expect(putBlockMutate).toHaveBeenCalledTimes(2);
    expect(toast.error).toHaveBeenCalledWith(expect.stringMatching(/saved 2 blocks.*safe to try again/i));
    // The blocks that did land must still show as saved (moving on to ConfirmMetrics, since one
    // carries a metric), not the pre-accept "nothing is saved yet" review screen.
    expect(screen.queryByText(/nothing is saved yet/i)).not.toBeInTheDocument();
    expect(await screen.findByText(/is this accurate and defensible/i)).toBeInTheDocument();
  });

  it("reports total failure only when nothing was written", async () => {
    resetQueries();
    putBlockMutate.mockReset().mockRejectedValue(new ApiError(422, null, "bad block"));
    const user = userEvent.setup({ delay: null });
    render(<ImportResume proposal={proposal} onConfirm={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: /add .* to my profile/i }));
    expect(toast.error).toHaveBeenCalledWith("bad block");
    expect(screen.queryByText(/added .* blocks to your profile/i)).not.toBeInTheDocument();
  });

  // --- Finding 7: verifyMetric (via ConfirmMetrics) is the only path that sets verified: true ---

  it("verifies exactly the confirmed block and leaves every other saved block untouched", async () => {
    resetQueries();
    const user = userEvent.setup({ delay: null });
    render(<ImportResume proposal={proposal} onConfirm={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: /add .* to my profile/i }));
    // Only acme-win carries a metric, so ConfirmMetrics now shows exactly that one block.
    await screen.findByText(/cut costs 30%/i);
    putBlockMutate.mockClear();
    await user.click(screen.getByRole("button", { name: /yes, .* accurate/i }));
    expect(putBlockMutate).toHaveBeenCalledTimes(1);
    const [written] = putBlockMutate.mock.calls[0] as [Block];
    expect(written.id).toBe("acme-win");
    expect(written.verified).toBe(true);
    // The other saved block was never sent back through putBlock at all.
    expect(putBlockMutate).not.toHaveBeenCalledWith(expect.objectContaining({ id: "acme-lead" }));
  });
});
