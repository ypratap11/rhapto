import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { RegenerateDialog } from "./RegenerateDialog";
import type { JobOut, PackageOut } from "@/lib/api/queries";

const mutateAsync = vi.fn();
let resumeDocument: { filename: string } | null = null;
let tracksData: { id: string; name: string; resume_base: string; keywords: string[]; min_fit: number; description: null }[] = [
  { id: "data-pm", name: "Data PM", resume_base: "data-pm", keywords: [], min_fit: 60, description: null },
];
vi.mock("@/lib/api/queries", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/queries")>()),
  useTailor: () => ({ mutateAsync, isPending: false }),
  useResumeDocument: () => ({ data: resumeDocument, isPending: false }),
  useTracks: () => ({ data: tracksData }),
}));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock("@/components/jobs/TaskProgress", () => ({ TaskProgress: () => <div>progress</div> }));

const job = { id: "j1" } as JobOut;
const pkg = { id: "p1", track_id: "data-pm", version: 1, mode: "blocks" } as PackageOut;

afterEach(() => {
  tracksData = [{ id: "data-pm", name: "Data PM", resume_base: "data-pm", keywords: [], min_fit: 60, description: null }];
  resumeDocument = null;
  mutateAsync.mockReset();
});

const BANNED = /\.env|RHAPTO_API_TOKEN|rapidapi_key|app_key|app_id|LLM|tokens|\bpoll|\bblocks?\b|\bbases?\b|\btracks?\b|guardrails?|provenance|verified|docs\/|database|rhapto profile/i;

describe("RegenerateDialog", () => {
  it("uses no technical words in the open dialog, in text or aria-labels", () => {
    resumeDocument = { filename: "Maya_Chen_Resume.docx" };
    render(<RegenerateDialog job={job} pkg={pkg} open onOpenChange={() => undefined} />);
    const dialog = screen.getByRole("dialog");
    const body = dialog.cloneNode(true) as HTMLElement;
    body.querySelectorAll("details").forEach((d) => d.remove());
    expect((body.textContent ?? "").match(BANNED)?.[0] ?? null).toBeNull();
    const labels = Array.from(body.querySelectorAll("[aria-label]")).map((el) => el.getAttribute("aria-label") ?? "");
    for (const label of labels) expect(label).not.toMatch(BANNED);
    // Not a vacuous pass: the dialog really rendered its form.
    expect(body.textContent).toMatch(/feedback/i);
  });

  it("requires feedback and posts it with the parent package id", async () => {
    mutateAsync.mockResolvedValueOnce({ id: "t1", status: "running" });
    render(<RegenerateDialog job={job} pkg={pkg} open onOpenChange={() => undefined} />);
    // delay: null skips the per-keystroke wait; typing a sentence char by char through jsdom
    // and Base UI was the slowest thing in the suite.
    const user = userEvent.setup({ delay: null });
    await user.click(screen.getByRole("button", { name: /regenerate/i }));
    expect(screen.getByText(/at least 10 characters/i)).toBeInTheDocument();
    await user.type(screen.getByLabelText(/feedback/i), "Lean harder on the migration work.");
    await user.click(screen.getByRole("button", { name: /regenerate/i }));
    expect(mutateAsync).toHaveBeenCalledWith({ jobId: "j1", body: { feedback: "Lean harder on the migration work.", parent_package_id: "p1", track_id: "data-pm", mode: "blocks" } });
    expect(await screen.findByText("progress")).toBeInTheDocument();
  });

  it("defaults to tune mode when a resume document exists, even for a blocks parent", async () => {
    resumeDocument = { filename: "Maya_Chen_Resume.docx" };
    mutateAsync.mockResolvedValueOnce({ id: "t2", status: "running" });
    render(<RegenerateDialog job={job} pkg={pkg} open onOpenChange={() => undefined} />);
    const user = userEvent.setup({ delay: null });
    expect(screen.getByRole("combobox", { name: "Mode" })).toHaveTextContent("Light touch");
    await user.type(screen.getByLabelText(/feedback/i), "Lean harder on the migration work.");
    await user.click(screen.getByRole("button", { name: /regenerate/i }));
    expect(mutateAsync).toHaveBeenCalledWith({ jobId: "j1", body: { feedback: "Lean harder on the migration work.", parent_package_id: "p1", track_id: "data-pm", mode: "tune" } });
    resumeDocument = null;
  });

  it("maps_an_empty_track_to_null_and_hides_the_picker_without_tracks", async () => {
    const emptyTrackPkg = { id: "p9", track_id: "", version: 1, mode: "tune" } as PackageOut;
    const user = userEvent.setup({ delay: null });

    // A tune package that never had a track, for a user who has none: no picker, and null goes out.
    tracksData = [];
    mutateAsync.mockResolvedValueOnce({ id: "t3", status: "running" });
    const first = render(<RegenerateDialog job={job} pkg={emptyTrackPkg} open onOpenChange={() => undefined} />);
    expect(screen.queryByLabelText("Role")).toBeNull();
    await user.type(screen.getByLabelText(/feedback/i), "Lean harder on the migration work.");
    await user.click(screen.getByRole("button", { name: /regenerate/i }));
    expect(mutateAsync).toHaveBeenLastCalledWith({
      jobId: "j1",
      body: { feedback: "Lean harder on the migration work.", parent_package_id: "p9", track_id: null, mode: "tune" },
    });
    first.unmount();

    // The same package for a user who has tracks since: the picker is back, and untouched it still sends null.
    tracksData = [{ id: "data-pm", name: "Data PM", resume_base: "data-pm", keywords: [], min_fit: 60, description: null }];
    mutateAsync.mockResolvedValueOnce({ id: "t4", status: "running" });
    render(<RegenerateDialog job={job} pkg={emptyTrackPkg} open onOpenChange={() => undefined} />);
    expect(screen.getByLabelText("Role")).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toHaveTextContent("Make a new version");
    expect(screen.getByLabelText("Role")).not.toHaveTextContent("data-pm");
    await user.type(screen.getByLabelText(/feedback/i), "Lean harder on the migration work.");
    await user.click(screen.getByRole("button", { name: /regenerate/i }));
    expect(mutateAsync).toHaveBeenLastCalledWith({
      jobId: "j1",
      body: { feedback: "Lean harder on the migration work.", parent_package_id: "p9", track_id: null, mode: "tune" },
    });
  });
});
