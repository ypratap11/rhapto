import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { RegenerateDialog } from "./RegenerateDialog";
import type { JobOut, PackageOut } from "@/lib/api/queries";

const mutateAsync = vi.fn();
vi.mock("@/lib/api/queries", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/queries")>()),
  useTailor: () => ({ mutateAsync, isPending: false }),
  useTracks: () => ({ data: [{ id: "data-pm", name: "Data PM", resume_base: "data-pm", keywords: [], min_fit: 60, description: null }] }),
}));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock("@/components/queue/TaskProgress", () => ({ TaskProgress: () => <div>progress</div> }));

const job = { id: "j1" } as JobOut;
const pkg = { id: "p1", track_id: "data-pm", version: 1 } as PackageOut;

describe("RegenerateDialog", () => {
  it("requires feedback and posts it with the parent package id", async () => {
    mutateAsync.mockResolvedValueOnce({ id: "t1", status: "running" });
    render(<RegenerateDialog job={job} pkg={pkg} open onOpenChange={() => undefined} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /regenerate/i }));
    expect(screen.getByText(/at least 10 characters/i)).toBeInTheDocument();
    await user.type(screen.getByLabelText(/feedback/i), "Lean harder on the migration work.");
    await user.click(screen.getByRole("button", { name: /regenerate/i }));
    expect(mutateAsync).toHaveBeenCalledWith({ jobId: "j1", body: { feedback: "Lean harder on the migration work.", parent_package_id: "p1", track_id: "data-pm" } });
    expect(await screen.findByText("progress")).toBeInTheDocument();
  });
});
