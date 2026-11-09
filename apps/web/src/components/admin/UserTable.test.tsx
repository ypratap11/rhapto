import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { UserTable } from "./UserTable";
import { mockFetch, renderWithClient } from "./test-utils";

const row = (id: string, email: string, extra = {}) => ({
  id, email, runs_used: 3, runs_limit: 3, failed_count: 1, last_seen_at: "2026-11-09T10:00:00Z", blocked: false, ...extra,
});
afterEach(() => vi.restoreAllMocks());

describe("UserTable", () => {
  it("debounces typing into one POST search with the term in the body, never the URL", async () => {
    const { calls } = mockFetch([["POST", "/users/search", 200, { users: [row("u1", "alex@example.com")], next_offset: null }]]);
    renderWithClient(<UserTable />);
    await screen.findByText("alex@example.com");
    const before = calls.length;
    await userEvent.type(screen.getByRole("searchbox"), "alex");
    await waitFor(() => expect(calls.length).toBe(before + 1));
    const last = calls[calls.length - 1]!;
    expect(last.method).toBe("POST");
    expect(last.body).toEqual({ q: "alex", offset: 0 });
    expect(last.url).not.toContain("alex");
    expect(window.location.search).toBe("");
  });
  it("links rows by id and marks blocked users", async () => {
    mockFetch([["POST", "/users/search", 200, { users: [row("u1", "a@example.com"), row("u2", "b@example.com", { blocked: true })], next_offset: null }]]);
    renderWithClient(<UserTable />);
    const link = await screen.findByRole("link", { name: "b@example.com" });
    expect(link.getAttribute("href")).toBe("/admin/users/u2");
    expect(screen.getAllByText("Blocked")).toHaveLength(1);
    expect(screen.getByText(/failed \(7 days\)/i)).toBeTruthy();
  });
  it("shows Load more only when next_offset is set and sends it", async () => {
    const { calls } = mockFetch([["POST", "/users/search", 200, { users: [row("u1", "a@example.com")], next_offset: 25 }]]);
    renderWithClient(<UserTable />);
    const more = await screen.findByRole("button", { name: "Load more" });
    await userEvent.click(more);
    await waitFor(() => expect(calls.some((c) => (c.body as { offset: number }).offset === 25)).toBe(true));
  });
  it("hides Load more on the last page", async () => {
    mockFetch([["POST", "/users/search", 200, { users: [row("u1", "a@example.com")], next_offset: null }]]);
    renderWithClient(<UserTable />);
    await screen.findByText("a@example.com");
    expect(screen.queryByRole("button", { name: "Load more" })).toBeNull();
  });
});
