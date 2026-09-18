import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { ApplicationOut } from "@/lib/api/queries";
import { StatusControl } from "./StatusControl";

const patch = vi.fn().mockResolvedValue({});
vi.mock("@/lib/api/queries", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/queries")>()),
  usePatchApplication: () => ({ mutateAsync: patch, isPending: false }),
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const application = {
  id: "a1",
  status: "applied",
  applied_at: "2026-09-10",
  notes: "",
  closed_reason: null,
  follow_up_at: null,
  status_history: [],
  job: { id: "j1", company: "ExampleCo", title: "TPM" },
  package_id: "p1",
  created_at: "2026-09-10T00:00:00Z",
  updated_at: "2026-09-10T00:00:00Z",
} as unknown as ApplicationOut;

describe("StatusControl", () => {
  it("advances the status", async () => {
    const user = userEvent.setup({ delay: null });
    render(<StatusControl application={application} />);
    await user.click(screen.getByLabelText("Status"));
    await user.click(await screen.findByRole("option", { name: "Interview" }));
    expect(patch).toHaveBeenCalledWith({ id: "a1", body: { status: "interview" } });
  });

  it("asks for a reason only when the status is Closed", async () => {
    const user = userEvent.setup({ delay: null });
    const { rerender } = render(<StatusControl application={application} />);
    expect(screen.queryByLabelText("Closed reason")).toBeNull();

    rerender(<StatusControl application={{ ...application, status: "closed" } as ApplicationOut} />);
    await user.click(screen.getByLabelText("Closed reason"));
    for (const label of ["Rejected", "Withdrew", "No response", "Filled"]) {
      expect(await screen.findByRole("option", { name: label })).toBeInTheDocument();
    }
    await user.click(screen.getByRole("option", { name: "No response" }));
    expect(patch).toHaveBeenCalledWith({ id: "a1", body: { closed_reason: "no_response" } });
  });

  it("saves a follow-up date, which the dashboard then reminds about", async () => {
    const user = userEvent.setup({ delay: null });
    render(<StatusControl application={application} />);
    await user.type(screen.getByLabelText("Follow up on"), "2026-09-21");
    await user.click(screen.getByRole("button", { name: /save follow-up/i }));
    expect(patch).toHaveBeenCalledWith({ id: "a1", body: { follow_up_at: "2026-09-21" } });
  });
});
