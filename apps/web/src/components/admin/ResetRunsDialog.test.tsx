import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ResetRunsDialog } from "./ResetRunsDialog";
import { mockFetch, renderWithClient } from "./test-utils";

afterEach(() => vi.restoreAllMocks());
const open = (extra = {}) =>
  renderWithClient(<ResetRunsDialog userId="u1" runsUsed={3} suggested={1} open onOpenChange={() => {}} {...extra} />);
const confirm = () => screen.getByRole("button", { name: "Reset" }) as HTMLButtonElement;

describe("ResetRunsDialog", () => {
  it("says up to N and disables confirm when the value equals the current one", () => {
    open({ suggested: null });
    expect(screen.getByText(/up to 3/i)).toBeTruthy();
    expect((screen.getByRole("spinbutton") as HTMLInputElement).value).toBe("3");
    expect(confirm().disabled).toBe(true);
  });
  it("pre-fills with the suggestion applied", () => {
    open();
    expect((screen.getByRole("spinbutton") as HTMLInputElement).value).toBe("2");
    expect(confirm().disabled).toBe(false);
  });
  it("cannot submit a value above the current", async () => {
    const { calls } = mockFetch([]);
    open();
    const input = screen.getByRole("spinbutton");
    await userEvent.clear(input);
    await userEvent.type(input, "9");
    expect(confirm().disabled).toBe(true);
    expect(input.getAttribute("max")).toBe("3");
    await userEvent.click(confirm());
    expect(calls).toHaveLength(0);
  });
  it("submits to", async () => {
    const { calls } = mockFetch([["POST", "/reset-runs", 200, { changed: true, runs_used: 2, blocked: null }]]);
    open();
    await userEvent.click(confirm());
    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0]?.body).toEqual({ to: 2 });
    expect(calls[0]?.url).toContain("/admin/users/u1/reset-runs");
  });
  it("shows the server's 409 sentence", async () => {
    mockFetch([["POST", "/reset-runs", 409, { title: "Conflict", status: 409, detail: "Runs used changed since you opened this." }]]);
    open();
    await userEvent.click(confirm());
    expect(await screen.findByText("Runs used changed since you opened this.")).toBeTruthy();
  });
});
