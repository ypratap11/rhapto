import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { UserPanel } from "./UserPanel";
import { mockFetch, renderWithClient } from "./test-utils";

const detail = {
  id: "u1", email: "alex@example.com", joined_at: "2026-11-03T10:00:00Z", runs_used: 3, runs_limit: 3,
  free_spend_usd: "0.94", asked_for_more: true, blocked: false, suggested_reset_runs: 2,
  failures: [
    { when: "2026-11-08T14:02:00Z", type: "tailor_job", category: "provider_error", label: "The AI provider timed out", error: "SECRET RAW TRACE" },
    { when: "2026-11-07T09:00:00Z", type: "tailor_job", category: "did_not_finish", label: "Stopped before it finished" },
  ],
  history: [{ when: "2026-11-08T15:00:00Z", actor_email: "owner@example.com", action: "reset_runs", before: { trial_runs_used: 3 }, after: { trial_runs_used: 1 } }],
};
afterEach(() => vi.restoreAllMocks());

describe("UserPanel", () => {
  it("shows labels only, marks did_not_finish, suggests up to N, lists history", async () => {
    mockFetch([["GET", "/admin/users/u1", 200, detail]]);
    renderWithClient(<UserPanel userId="u1" />);
    expect(await screen.findByText("The AI provider timed out")).toBeTruthy();
    expect(screen.queryByText(/SECRET RAW TRACE/)).toBeNull();
    expect(screen.queryByText("provider_error")).toBeNull();
    expect(screen.getByText("Never finished")).toBeTruthy();
    expect(screen.getByText(/up to 2/i)).toBeTruthy();
    expect(screen.getByText("owner@example.com")).toBeTruthy();
    expect(screen.getByRole("cell", { name: "Reset free runs" })).toBeTruthy();
    expect(screen.getByText(/3 → 1/)).toBeTruthy();
  });
  it("Block asks first and sends nothing until confirmed", async () => {
    const { calls } = mockFetch([["GET", "/admin/users/u1", 200, detail], ["POST", "/block", 200, { changed: true, runs_used: null, blocked: true }]]);
    renderWithClient(<UserPanel userId="u1" />);
    await userEvent.click(await screen.findByRole("button", { name: "Block user" }));
    expect(await screen.findByText(/Block alex@example.com\?/)).toBeTruthy();
    expect(calls.some((c) => c.method === "POST")).toBe(false);
    await userEvent.click(screen.getByRole("button", { name: "Block" }));
    await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.url.endsWith("/block"))).toBe(true));
  });
  it("a 409 from block says admin accounts cannot be blocked", async () => {
    mockFetch([["GET", "/admin/users/u1", 200, detail], ["POST", "/block", 409, { title: "Conflict", status: 409, detail: "x" }]]);
    renderWithClient(<UserPanel userId="u1" />);
    await userEvent.click(await screen.findByRole("button", { name: "Block user" }));
    await userEvent.click(await screen.findByRole("button", { name: "Block" }));
    expect(await screen.findByText("Admin accounts cannot be blocked")).toBeTruthy();
  });
});
