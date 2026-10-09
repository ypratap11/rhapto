import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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

// `SAME_ORIGIN_DEPLOYMENT` is a build-time const; a getter mock is the only way to see both modes
// (the pattern Landing.test.tsx and TokenGate.test.tsx use).
const sameOrigin = { value: true };
vi.mock("@/lib/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/client")>();
  return {
    ...actual,
    get SAME_ORIGIN_DEPLOYMENT() {
      return sameOrigin.value;
    },
  };
});

const pathname = vi.fn(() => "/start");
vi.mock("next/navigation", () => ({ usePathname: () => pathname() }));

describe("TopBar", () => {
  it("lists the three coach tabs in order and marks the current one", () => {
    pathname.mockReturnValue("/resumes");
    render(<TopBar />);
    const nav = screen.getByRole("navigation", { name: "Primary" });
    expect([...nav.querySelectorAll("a")].map((a) => a.textContent)).toEqual([
      "Tailor a resume",
      "My resumes",
      "Feedback",
    ]);
    expect(screen.getByRole("link", { name: "My resumes" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Tailor a resume" })).toHaveAttribute("href", "/start");
    expect(screen.getByRole("link", { name: "Tailor a resume" })).not.toHaveAttribute("aria-current");
    expect(screen.getByRole("link", { name: "Feedback" })).toHaveAttribute("href", "/feedback");
  });

  it("marks Tailor a resume current on /start and nothing current on /", () => {
    pathname.mockReturnValue("/start");
    const { unmount } = render(<TopBar />);
    expect(screen.getByRole("link", { name: "Tailor a resume" })).toHaveAttribute("aria-current", "page");
    unmount();
    pathname.mockReturnValue("/");
    render(<TopBar />);
    expect(screen.getByRole("link", { name: "Tailor a resume" })).not.toHaveAttribute("aria-current");
  });

  it("keeps the old tabs out of the primary nav and behind Advanced, closed by default", async () => {
    pathname.mockReturnValue("/start");
    render(<TopBar />);
    const nav = screen.getByRole("navigation", { name: "Primary" });
    for (const old of ["Dashboard", "Jobs", "Pipeline", "Profile"]) {
      expect(within(nav).queryByRole("link", { name: old })).toBeNull();
      expect(screen.queryByRole("link", { name: old })).toBeNull(); // menu closed
    }
    const trigger = screen.getByRole("button", { name: /advanced/i });
    expect(trigger).toHaveAttribute("aria-expanded", "false");

    const user = userEvent.setup({ delay: null });
    await user.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "true");
    const menu = screen.getByRole("list", { name: "Advanced" });
    expect([...menu.querySelectorAll("a")].map((a) => [a.textContent, a.getAttribute("href")])).toEqual([
      ["Dashboard", "/dashboard"],
      ["Jobs", "/jobs"],
      ["Pipeline", "/pipeline"],
      ["Profile", "/profile"],
    ]);
  });

  it("closes the Advanced menu on Escape and marks the trigger active on an advanced page", async () => {
    pathname.mockReturnValue("/jobs/abc");
    render(<TopBar />);
    const trigger = screen.getByRole("button", { name: /advanced/i });
    expect(trigger).toHaveAttribute("data-active", "true");
    const user = userEvent.setup({ delay: null });
    await user.click(trigger);
    expect(screen.getByRole("link", { name: "Jobs" })).toHaveAttribute("aria-current", "page");
    await user.keyboard("{Escape}");
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("link", { name: "Jobs" })).toBeNull();
  });

  it("points the logo at /start in hosted mode and at /dashboard in token mode", () => {
    pathname.mockReturnValue("/start");
    sameOrigin.value = true;
    const { unmount } = render(<TopBar />);
    expect(screen.getByRole("link", { name: "Rhapto" })).toHaveAttribute("href", "/start");
    unmount();
    sameOrigin.value = false;
    render(<TopBar />);
    expect(screen.getByRole("link", { name: "Rhapto" })).toHaveAttribute("href", "/dashboard");
  });

  it("offers the theme toggle, Settings and Help", () => {
    render(<TopBar />);
    expect(screen.getByRole("button", { name: /toggle theme/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Settings" })).toHaveAttribute("href", "/settings");
    expect(screen.getByRole("link", { name: "Help" })).toHaveAttribute("href", "/settings#help");
  });

  it("orders the trailing icon controls as theme toggle, then Settings, then Help", () => {
    render(<TopBar />);
    const trailing = [...screen.getByRole("banner").querySelectorAll("button[aria-label], a[aria-label]")].map((el) =>
      el.getAttribute("aria-label"),
    );
    expect(trailing).toEqual(["Toggle theme", "Settings", "Help"]);
  });

  it("shows the feedback button, by its aria-label, before the theme toggle", async () => {
    realButton.on = true;
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
    await screen.findByRole("button", { name: "Feedback on this page" });
    const trailing = [...screen.getByRole("banner").querySelectorAll("button[aria-label], a[aria-label]")].map((el) =>
      el.getAttribute("aria-label"),
    );
    expect(trailing).toEqual(["Feedback on this page", "Toggle theme", "Settings", "Help"]);
  });

  it("lets the tabs drop to their own sideways-scrolling row on phones instead of overflowing the bar", () => {
    // jsdom cannot measure layout; this pins the classes that do the work (PR #6).
    render(<TopBar />);
    const nav = screen.getByRole("navigation", { name: "Primary" });
    expect(nav.className.split(" ")).toEqual(expect.arrayContaining(["w-full", "overflow-x-auto"]));
    expect(nav.parentElement?.className.split(" ")).toEqual(expect.arrayContaining(["flex-wrap", "md:flex-nowrap"]));
  });
});

afterEach(() => {
  realButton.on = false;
  sameOrigin.value = true;
  vi.unstubAllGlobals();
  window.localStorage.clear();
});
