import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ApplicationOut } from "@/lib/api/queries";
import { ApplicationSheet } from "./ApplicationSheet";

const patch = vi.fn();
const remove = vi.fn();
vi.mock("@/lib/api/queries", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/queries")>()),
  usePatchApplication: () => ({ mutateAsync: patch, isPending: false }),
  useDeleteApplication: () => ({ mutateAsync: remove, isPending: false }),
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const application = {
  id: "a1",
  status: "applied",
  applied_at: "2026-09-10",
  notes: "",
  closed_reason: null,
  follow_up_at: null,
  status_history: [
    { status: "applied", at: "2026-09-10T00:00:00Z" },
    { status: "screen", at: "2026-09-12T00:00:00Z" },
    { status: "interview", at: "2026-09-15T00:00:00Z" },
  ],
  job: { id: "j1", company: "ExampleCo", title: "TPM" },
  package_id: "p1",
  created_at: "2026-09-10T00:00:00Z",
  updated_at: "2026-09-10T00:00:00Z",
} as unknown as ApplicationOut;

function open(a: ApplicationOut = application, onOpenChange = vi.fn()) {
  render(<ApplicationSheet application={a} open onOpenChange={onOpenChange} />);
  return onOpenChange;
}

beforeEach(() => {
  patch.mockReset().mockResolvedValue({});
  remove.mockReset().mockResolvedValue(undefined);
});

describe("ApplicationSheet", () => {
  it("is titled with the company and shows the role", () => {
    open();
    expect(screen.getByRole("dialog", { name: "ExampleCo" })).toBeInTheDocument();
    expect(screen.getByText("TPM")).toBeInTheDocument();
  });

  it("moves the status in words", async () => {
    const user = userEvent.setup({ delay: null });
    open();
    await user.click(screen.getByRole("combobox", { name: "Status" }));
    await user.click(await screen.findByRole("option", { name: "Interviewing" }));
    expect(patch).toHaveBeenCalledWith({ id: "a1", body: { status: "interview" } });
  });

  it("asks why on a closed application", async () => {
    const user = userEvent.setup({ delay: null });
    open({ ...application, status: "closed" } as ApplicationOut);
    await user.click(screen.getByRole("combobox", { name: "Closed reason" }));
    await user.click(await screen.findByRole("option", { name: "Withdrew" }));
    expect(patch).toHaveBeenCalledWith({ id: "a1", body: { closed_reason: "withdrew" } });
  });

  it("saves notes", async () => {
    const user = userEvent.setup({ delay: null });
    open();
    await user.type(screen.getByLabelText("Notes"), "Call on Friday");
    await user.click(screen.getByRole("button", { name: "Save notes" }));
    expect(patch).toHaveBeenCalledWith({ id: "a1", body: { notes: "Call on Friday" } });
  });

  it("saves a follow-up date", async () => {
    const user = userEvent.setup({ delay: null });
    open();
    await user.type(screen.getByLabelText("Follow up on"), "2026-10-20");
    await user.click(screen.getByRole("button", { name: "Save follow-up" }));
    expect(patch).toHaveBeenCalledWith({ id: "a1", body: { follow_up_at: "2026-10-20" } });
  });

  it("writes the history in words", () => {
    open();
    expect(screen.getByText("Screening")).toBeInTheDocument();
    const history = screen.getByRole("list");
    expect(history).toHaveTextContent("Interviewing");
    expect(history).not.toHaveTextContent(/\binterview\b/);
  });

  it("links to the resume used, and only when there is one", () => {
    const { unmount } = render(<ApplicationSheet application={application} open onOpenChange={vi.fn()} />);
    expect(screen.getByRole("link", { name: "Open the resume used" })).toHaveAttribute("href", "/jobs/j1/packages/p1");
    unmount();
    open({ ...application, package_id: null } as ApplicationOut);
    expect(screen.queryByRole("link", { name: "Open the resume used" })).toBeNull();
  });

  it("always links to the job, even with no resume; links are visible and 44px", () => {
    const { unmount } = render(<ApplicationSheet application={application} open onOpenChange={vi.fn()} />);
    const view = screen.getByRole("link", { name: "View the job" });
    expect(view).toHaveAttribute("href", "/jobs/j1");
    for (const l of [view, screen.getByRole("link", { name: "Open the resume used" })]) {
      expect(l.className).not.toMatch(/text-accent/);
      expect(l.className).toMatch(/text-primary/);
      expect(l.className).toMatch(/min-h-11/);
    }
    unmount();
    open({ ...application, package_id: null } as ApplicationOut);
    expect(screen.getByRole("link", { name: "View the job" })).toHaveAttribute("href", "/jobs/j1");
  });

  it("removes the application after confirming, and closes", async () => {
    const user = userEvent.setup({ delay: null });
    const onOpenChange = open();
    await user.click(screen.getByRole("button", { name: "Delete" }));
    expect(await screen.findByText("Remove this application?")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Remove" }));
    expect(remove).toHaveBeenCalledWith("a1");
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });
});
