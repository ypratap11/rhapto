import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { ResumeImportOut } from "@/lib/api/queries";
import { ImportResume } from "./ImportResume";

// ImportResume writes the accepted proposal via the profile mutation hooks (usePutBlock,
// usePutTrack, usePutAnswers) once the user confirms, and reads useAnswers/useBases to do it
// safely (merging location answers, picking a base for a proposed track). None of that needs a
// real QueryClient here — following BlocksTab.test.tsx's convention, the hooks are replaced with
// plain stubs so the component under test never touches react-query or the network.
const putBlockMutate = vi.fn().mockResolvedValue({});
const putTrackMutate = vi.fn().mockResolvedValue({});
const putAnswersMutate = vi.fn().mockResolvedValue({});

vi.mock("@/lib/api/queries", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/queries")>()),
  useAnswers: () => ({ data: {}, isLoading: false, error: null }),
  useBases: () => ({ data: [], isLoading: false, error: null }),
  usePutBlock: () => ({ mutateAsync: putBlockMutate, isPending: false }),
  usePutTrack: () => ({ mutateAsync: putTrackMutate, isPending: false }),
  usePutAnswers: () => ({ mutateAsync: putAnswersMutate, isPending: false }),
}));

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const proposal: ResumeImportOut = {
  blocks: [
    {
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
    },
    {
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
    },
  ],
  tracks: [{ id: "tpm", name: "TPM", keywords: [], field: "program-project-management", role: "technical-program-manager" }],
  location: { location_home: "Dublin, CA", location_preferred: [], remote_ok: "yes" },
  dropped_periods: 1,
  metrics_to_confirm: 1,
};

describe("ImportResume", () => {
  it("shows every proposed block before anything is saved", () => {
    render(<ImportResume proposal={proposal} onConfirm={vi.fn()} />);
    expect(screen.getByText("Delivery Lead")).toBeInTheDocument();
    expect(screen.getByText(/Cut costs 30%/)).toBeInTheDocument();
  });

  it("marks blocks whose date could not be read", () => {
    render(<ImportResume proposal={proposal} onConfirm={vi.fn()} />);
    expect(screen.getByText(/1 .*no date/i)).toBeInTheDocument();
  });

  it("says nothing is saved until the user confirms", () => {
    render(<ImportResume proposal={proposal} onConfirm={vi.fn()} />);
    expect(screen.getByText(/nothing is saved yet/i)).toBeInTheDocument();
  });

  it("passes the proposal to onConfirm when accepted", async () => {
    const onConfirm = vi.fn();
    const user = userEvent.setup({ delay: null });
    render(<ImportResume proposal={proposal} onConfirm={onConfirm} />);
    await user.click(screen.getByRole("button", { name: /add .* to my profile/i }));
    expect(onConfirm).toHaveBeenCalledWith(proposal);
  });
});
