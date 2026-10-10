import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { TopBar } from "./TopBar";
import { setSettings } from "@/lib/api/client";
import visibility from "@/lib/edge-visibility.json";

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

vi.mock("next/link", () => ({
  default: ({ prefetch, href, children, ...rest }: { prefetch?: boolean | null; href: string; children: React.ReactNode } & Record<string, unknown>) => (
    <a href={href} data-link="1" data-prefetch={String(prefetch)} {...rest}>
      {children}
    </a>
  ),
}));

/** Real <Link>s (data-link) to a protected route whose prefetch is not exactly false. */
function prefetchedProtectedLinks(root: ParentNode): string[] {
  const protectedHref = (h: string | null) => !!h && visibility.protectedAtEdge.some((p) => h === p || h.startsWith(`${p}/`) || h.startsWith(`${p}#`));
  return [...root.querySelectorAll<HTMLAnchorElement>("a[data-link]")]
    .filter((a) => protectedHref(a.getAttribute("href")))
    .filter((a) => a.getAttribute("data-prefetch") !== "false")
    .map((a) => a.getAttribute("href")!);
}

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

  it("marks Tailor a resume current on /start; the visitor header on / has no tabs", () => {
    pathname.mockReturnValue("/start");
    const { unmount } = render(<TopBar />);
    expect(screen.getByRole("link", { name: "Tailor a resume" })).toHaveAttribute("aria-current", "page");
    unmount();
    pathname.mockReturnValue("/");
    render(<TopBar />);
    expect(screen.queryByRole("link", { name: "Tailor a resume" })).toBeNull();
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

  it("points the logo at / in both modes and on every kind of page", () => {
    for (const path of ["/", "/start", "/settings"]) {
      for (const hosted of [true, false]) {
        pathname.mockReturnValue(path);
        sameOrigin.value = hosted;
        const { unmount } = render(<TopBar />);
        expect(screen.getByRole("link", { name: "Rhapto" })).toHaveAttribute("href", "/");
        unmount();
      }
    }
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
    expect(trailing).toEqual(["Toggle theme", "Settings", "Help", "Menu"]);
  });

  it("shows the feedback button, by its aria-label, before the theme toggle", async () => {
    pathname.mockReturnValue("/start"); // not left over from an earlier test
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
    expect(trailing).toEqual(["Feedback on this page", "Toggle theme", "Settings", "Help", "Menu"]);
  });

  it("is one row on every width: nav and icons hidden below md, Menu hidden from md, 44px phone targets", () => {
    // jsdom cannot measure layout; this pins the classes that do the work.
    pathname.mockReturnValue("/start");
    render(<TopBar />);
    const nav = screen.getByRole("navigation", { name: "Primary" });
    expect(nav.className.split(" ")).toEqual(expect.arrayContaining(["hidden", "md:flex"]));
    expect(nav.className).not.toContain("overflow-x-auto");
    expect(screen.getByRole("link", { name: "Settings" }).parentElement!.className).toContain("hidden");
    const menu = screen.getByRole("button", { name: "Menu" });
    expect(menu.className).toContain("md:hidden");
    expect(menu.className).toContain("size-11");
    expect(screen.getByRole("link", { name: "Rhapto" }).className).toContain("min-h-11");
    expect(screen.getByRole("banner").firstElementChild!.className).not.toContain("flex-wrap");
  });

  describe("visitor header (/ and token-mode /settings without a token)", () => {
    const hrefs = () => [...screen.getByRole("banner").querySelectorAll("a")].map((a) => [a.textContent, a.getAttribute("href")]);
    const buttonNames = () => [...screen.getByRole("banner").querySelectorAll("button")].map((b) => b.getAttribute("aria-label"));

    it("hosted /: exactly logo -> /, theme toggle and Sign in -> /start; nothing else", () => {
      pathname.mockReturnValue("/");
      sameOrigin.value = true;
      render(<TopBar />);
      expect(hrefs()).toEqual([["Rhapto", "/"], ["Sign in", "/start"]]);
      expect(buttonNames()).toEqual(["Toggle theme", "Menu"]);
      expect(screen.queryByRole("navigation", { name: "Primary" })).toBeNull();
      expect(screen.queryByRole("button", { name: /advanced/i })).toBeNull();
      expect(screen.queryByRole("link", { name: /settings|help|about/i })).toBeNull();
    });

    it("token mode /: logo and Get started -> /settings", () => {
      pathname.mockReturnValue("/");
      sameOrigin.value = false;
      render(<TopBar />);
      expect(hrefs()).toEqual([["Rhapto", "/"], ["Get started", "/settings"]]);
    });

    it("token mode /settings without a token: visitor header, no link to itself", () => {
      pathname.mockReturnValue("/settings");
      sameOrigin.value = false;
      render(<TopBar />);
      expect(hrefs()).toEqual([["Rhapto", "/"]]);
      expect(screen.queryByRole("navigation", { name: "Primary" })).toBeNull();
    });

    it("token mode /settings WITH a token keeps the app header", () => {
      setSettings({ token: "tok", apiUrl: "http://localhost:8000" });
      pathname.mockReturnValue("/settings");
      sameOrigin.value = false;
      render(<TopBar />);
      expect(screen.getByRole("navigation", { name: "Primary" })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /advanced/i })).toBeInTheDocument();
    });

    it("hosted /settings is an in-app screen: tabs and Advanced present", () => {
      pathname.mockReturnValue("/settings");
      sameOrigin.value = true;
      render(<TopBar />);
      expect(screen.getByRole("navigation", { name: "Primary" })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /advanced/i })).toBeInTheDocument();
    });

    it("every protected link in the visitor header has prefetch disabled", () => {
      for (const hosted of [true, false]) {
        pathname.mockReturnValue("/");
        sameOrigin.value = hosted;
        const { container, unmount } = render(<TopBar />);
        expect(container.querySelectorAll("a[data-link]").length).toBeGreaterThan(1);
        expect(prefetchedProtectedLinks(container)).toEqual([]);
        unmount();
      }
    });

    it("the prefetch helper FAILS on a bare Link to a protected route (proof the check can fail)", () => {
      const { container } = render(
        <div>
          <a href="/start" data-link="1" data-prefetch="undefined">x</a>
          <a href="/resumes" data-link="1" data-prefetch="false">y</a>
          <a href="/start">plain anchor is fine</a>
        </div>,
      );
      expect(prefetchedProtectedLinks(container)).toEqual(["/start"]);
    });
  });

  describe("phone menu", () => {
    const open = async () => {
      const user = userEvent.setup({ delay: null });
      await user.click(screen.getByRole("button", { name: "Menu" }));
      return { user, dialog: await screen.findByRole("dialog", { name: "Menu" }) };
    };

    it("is a closed button named Menu (aria-expanded=false) that opens a dialog titled Menu (aria-expanded=true)", async () => {
      pathname.mockReturnValue("/start");
      render(<TopBar />);
      const trigger = screen.getByRole("button", { name: "Menu" });
      expect(trigger).toHaveAttribute("aria-expanded", "false");
      expect(screen.queryByRole("dialog")).toBeNull();
      const { dialog } = await open();
      expect(dialog).toBeInTheDocument();
      expect(trigger).toHaveAttribute("aria-expanded", "true");
    });

    it("in-app: tabs, Advanced pages, Settings, Help and the theme toggle", async () => {
      pathname.mockReturnValue("/start");
      render(<TopBar />);
      const { dialog } = await open();
      expect(within(dialog).getAllByRole("link").map((a) => [a.textContent, a.getAttribute("href")])).toEqual([
        ["Tailor a resume", "/start"],
        ["My resumes", "/resumes"],
        ["Feedback", "/feedback"],
        ["Dashboard", "/dashboard"],
        ["Jobs", "/jobs"],
        ["Pipeline", "/pipeline"],
        ["Profile", "/profile"],
        ["Settings", "/settings"],
        ["Help", "/settings#help"],
      ]);
      expect(within(dialog).getByRole("link", { name: "Tailor a resume" })).toHaveAttribute("aria-current", "page");
      expect(within(dialog).getByRole("button", { name: /toggle theme/i })).toBeInTheDocument();
    });

    it("visitor, hosted: Sign in, Request beta access, theme toggle; no app links", async () => {
      pathname.mockReturnValue("/");
      sameOrigin.value = true;
      render(<TopBar />);
      const { dialog } = await open();
      const links = within(dialog).getAllByRole("link");
      expect(links.map((a) => a.textContent)).toEqual(["Sign in", "Request beta access"]);
      expect(links[0]).toHaveAttribute("href", "/start");
      expect(links[0]).toHaveAttribute("data-prefetch", "false");
      expect(within(dialog).getByRole("button", { name: /toggle theme/i })).toBeInTheDocument();
    });

    it("visitor, token mode: Get started and the theme toggle only", async () => {
      pathname.mockReturnValue("/");
      sameOrigin.value = false;
      render(<TopBar />);
      const { dialog } = await open();
      expect(within(dialog).getAllByRole("link").map((a) => a.textContent)).toEqual(["Get started"]);
    });

    it("visitor menu has 44px tap targets for its links; no empty row on token-mode /settings", async () => {
      pathname.mockReturnValue("/");
      sameOrigin.value = true;
      const { unmount } = render(<TopBar />);
      let { dialog } = await open();
      for (const a of within(dialog).getAllByRole("link")) expect(a.className).toContain("min-h-11");
      unmount();
      pathname.mockReturnValue("/settings");
      sameOrigin.value = false;
      render(<TopBar />);
      ({ dialog } = await open());
      expect(within(dialog).queryAllByRole("link")).toHaveLength(0);
      expect(dialog.querySelectorAll("li")).toHaveLength(1); // only the theme toggle row
    });

    it("closes on Escape", async () => {
      pathname.mockReturnValue("/start");
      render(<TopBar />);
      const { user } = await open();
      await user.keyboard("{Escape}");
      await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
      expect(screen.getByRole("button", { name: "Menu" })).toHaveAttribute("aria-expanded", "false");
    });

    it("closes when a link is clicked, even a hash link that leaves the pathname unchanged", async () => {
      pathname.mockReturnValue("/settings");
      sameOrigin.value = true;
      render(<TopBar />);
      const { user, dialog } = await open();
      await user.click(within(dialog).getByRole("link", { name: "Help" }));
      await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    });

    it("closes when the route changes", async () => {
      pathname.mockReturnValue("/start");
      const { rerender } = render(<TopBar />);
      await open();
      pathname.mockReturnValue("/resumes");
      rerender(<TopBar />);
      expect(screen.queryByRole("dialog")).toBeNull();
    });

    it("in-app, the feedback button stays in the one-row bar, not inside the sheet", async () => {
      realButton.on = true;
      setSettings({ token: "tok", apiUrl: "http://localhost:8000" });
      vi.stubGlobal(
        "fetch",
        vi.fn(async () =>
          new Response(JSON.stringify({ auth_mode: "token", email: "t@example.com", llm_configured: true, user_id: "11111111-1111-4111-8111-111111111111" }), {
            status: 200,
            headers: { "content-type": "application/json" },
          }),
        ),
      );
      pathname.mockReturnValue("/start");
      render(
        <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
          <TopBar />
        </QueryClientProvider>,
      );
      const bar = await screen.findByRole("button", { name: "Feedback on this page" });
      expect(bar.closest("[role='dialog']")).toBeNull();
      expect(bar.parentElement!.className).not.toContain("hidden"); // not inside the md-only group
    });
  });
});

afterEach(() => {
  realButton.on = false;
  sameOrigin.value = true;
  vi.unstubAllGlobals();
  window.localStorage.clear();
});
