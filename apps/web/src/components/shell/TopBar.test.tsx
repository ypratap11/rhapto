import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { TopBar } from "./TopBar";
import { setSettings } from "@/lib/api/client";

// Most TopBar tests render <TopBar/> with no QueryClientProvider, which the real button (it calls
// useMe) needs; stub it to nothing there, and let one test opt in to the real component.
const realButton = { on: false };
vi.mock("@/components/feedback/FeedbackButton", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/components/feedback/FeedbackButton")>();
  return { FeedbackButton: () => (realButton.on ? <actual.FeedbackButton /> : null) };
});

const pathname = vi.fn(() => "/jobs");
vi.mock("next/navigation", () => ({ usePathname: () => pathname() }));

describe("TopBar", () => {
  it("lists the five portal tabs in order and marks the current one", () => {
    render(<TopBar />);
    const nav = screen.getByRole("navigation", { name: "Primary" });
    expect([...nav.querySelectorAll("a")].map((a) => a.textContent)).toEqual([
      "Dashboard",
      "Jobs",
      "Resumes",
      "Pipeline",
      "Profile",
    ]);
    expect(screen.getByRole("link", { name: "Jobs" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Dashboard" })).not.toHaveAttribute("aria-current");
  });

  it("points the Dashboard tab at /dashboard and marks it current there", () => {
    pathname.mockReturnValue("/dashboard");
    render(<TopBar />);
    expect(screen.getByRole("link", { name: "Dashboard" })).toHaveAttribute("href", "/dashboard");
    expect(screen.getByRole("link", { name: "Dashboard" })).toHaveAttribute("aria-current", "page");
  });

  it("does not mark Dashboard current at /", () => {
    pathname.mockReturnValue("/");
    render(<TopBar />);
    expect(screen.getByRole("link", { name: "Dashboard" })).not.toHaveAttribute("aria-current");
  });

  it("points the logo at /dashboard, not /, so a signed-in person's way back is the app, not the pitch", () => {
    pathname.mockReturnValue("/dashboard");
    render(<TopBar />);
    expect(screen.getByRole("link", { name: "Rhapto" })).toHaveAttribute("href", "/dashboard");
  });

  it("offers the theme toggle, Settings and Help", () => {
    pathname.mockReturnValue("/dashboard");
    render(<TopBar />);
    expect(screen.getByRole("button", { name: /toggle theme/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Settings" })).toHaveAttribute("href", "/settings");
    expect(screen.getByRole("link", { name: "Help" })).toHaveAttribute("href", "/settings#help");
  });

  it("orders the trailing controls as theme toggle, then Settings, then Help", () => {
    pathname.mockReturnValue("/dashboard");
    render(<TopBar />);
    const trailing = [...screen.getByRole("banner").querySelectorAll("button, a[aria-label]")].map((el) =>
      el.getAttribute("aria-label"),
    );
    expect(trailing).toEqual(["Toggle theme", "Settings", "Help"]);
  });

  it("shows the feedback button, by its aria-label, before the theme toggle on /dashboard", async () => {
    realButton.on = true;
    pathname.mockReturnValue("/dashboard");
    setSettings({ token: "tok", apiUrl: "http://localhost:8000" });
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(
          JSON.stringify({ auth_mode: "token", email: "tester-a@example.com", llm_configured: true, user_id: "11111111-1111-4111-8111-111111111111" }),
          { status: 200, headers: { "content-type": "application/json" } },
        ),
      ),
    );
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <TopBar />
      </QueryClientProvider>,
    );
    const button = await screen.findByRole("button", { name: "Feedback on this page" });
    const trailing = [...screen.getByRole("banner").querySelectorAll("button, a[aria-label]")].map((el) =>
      el.getAttribute("aria-label"),
    );
    expect(trailing).toEqual(["Feedback on this page", "Toggle theme", "Settings", "Help"]);
    expect(button).toBeInTheDocument();
  });
});

afterEach(() => {
  realButton.on = false;
  vi.unstubAllGlobals();
  window.localStorage.clear();
});
