import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { activeTab, TopBar } from "./TopBar";
import { setSettings } from "@/lib/api/client";
import visibility from "@/lib/edge-visibility.json";

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

/** Visitor tests: TopBar now calls useMe (disabled for visitors, so no request), which needs a client. */
function renderPlain() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <TopBar />
    </QueryClientProvider>,
  );
}

function renderBar(authMode: "access" | "token" = "access") {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () =>
      new Response(JSON.stringify({ auth_mode: authMode, email: "maya@example.com", llm_configured: true, user_id: "11111111-1111-4111-8111-111111111111" }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    ),
  );
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <TopBar />
    </QueryClientProvider>,
  );
}

describe("TopBar", () => {
  it("the visitor header on / has no tabs", () => {
    pathname.mockReturnValue("/");
    renderPlain();
    expect(screen.queryByRole("link", { name: "Tailor a resume" })).toBeNull();
    expect(screen.queryByRole("navigation", { name: "Primary" })).toBeNull();
  });

  it("points the visitor logo at /", () => {
    for (const hosted of [true, false]) {
      pathname.mockReturnValue("/");
      sameOrigin.value = hosted;
      const { unmount } = renderPlain();
      expect(screen.getByRole("link", { name: "Rhapto" })).toHaveAttribute("href", "/");
      unmount();
    }
  });

  describe("visitor header (/ and token-mode /settings without a token)", () => {
    const hrefs = () => [...screen.getByRole("banner").querySelectorAll("a")].map((a) => [a.textContent, a.getAttribute("href")]);
    const buttonNames = () => [...screen.getByRole("banner").querySelectorAll("button")].map((b) => b.getAttribute("aria-label"));

    it("hosted /: exactly logo -> /, theme toggle and Sign in -> /dashboard; nothing else", () => {
      pathname.mockReturnValue("/");
      sameOrigin.value = true;
      renderPlain();
      expect(hrefs()).toEqual([["Rhapto", "/"], ["Sign in", "/dashboard"]]);
      expect(buttonNames()).toEqual(["Toggle theme", "Menu"]);
      expect(screen.queryByRole("navigation", { name: "Primary" })).toBeNull();
      expect(screen.queryByRole("button", { name: /advanced/i })).toBeNull();
      expect(screen.queryByRole("link", { name: /settings|help|about/i })).toBeNull();
    });

    it("token mode /: logo and Get started -> /settings", () => {
      pathname.mockReturnValue("/");
      sameOrigin.value = false;
      renderPlain();
      expect(hrefs()).toEqual([["Rhapto", "/"], ["Get started", "/settings"]]);
    });

    it("token mode /settings without a token: visitor header, no link to itself", () => {
      pathname.mockReturnValue("/settings");
      sameOrigin.value = false;
      renderPlain();
      expect(hrefs()).toEqual([["Rhapto", "/"]]);
      expect(screen.queryByRole("navigation", { name: "Primary" })).toBeNull();
    });

    it("token mode /settings WITH a token keeps the app header", () => {
      setSettings({ token: "tok", apiUrl: "http://localhost:8000" });
      pathname.mockReturnValue("/settings");
      sameOrigin.value = false;
      renderBar("token");
      expect(within(screen.getByRole("navigation", { name: "Primary" })).getAllByRole("link").map((a) => a.textContent)).toEqual(["Dashboard", "My resumes"]);
      expect(screen.queryByRole("button", { name: /advanced/i })).toBeNull();
    });

    it("hosted /settings is an in-app screen: two tabs, no Advanced", () => {
      pathname.mockReturnValue("/settings");
      sameOrigin.value = true;
      renderBar();
      expect(within(screen.getByRole("navigation", { name: "Primary" })).getAllByRole("link").map((a) => a.textContent)).toEqual(["Dashboard", "My resumes"]);
      expect(screen.queryByRole("button", { name: /advanced/i })).toBeNull();
    });

    it("every protected link in the visitor header has prefetch disabled", () => {
      for (const hosted of [true, false]) {
        pathname.mockReturnValue("/");
        sameOrigin.value = hosted;
        const { container, unmount } = renderPlain();
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
      pathname.mockReturnValue("/dashboard");
      renderBar();
      const trigger = screen.getByRole("button", { name: "Menu" });
      expect(trigger).toHaveAttribute("aria-expanded", "false");
      expect(screen.queryByRole("dialog")).toBeNull();
      const { dialog } = await open();
      expect(dialog).toBeInTheDocument();
      expect(trigger).toHaveAttribute("aria-expanded", "true");
    });

    it("visitor, hosted: Sign in, Request beta access, theme toggle; no app links", async () => {
      pathname.mockReturnValue("/");
      sameOrigin.value = true;
      renderPlain();
      const { dialog } = await open();
      const links = within(dialog).getAllByRole("link");
      expect(links.map((a) => a.textContent)).toEqual(["Sign in", "Request beta access"]);
      expect(links[0]).toHaveAttribute("href", "/dashboard");
      expect(links[0]).toHaveAttribute("data-prefetch", "false");
      expect(within(dialog).getByRole("button", { name: /toggle theme/i })).toBeInTheDocument();
    });

    it("visitor, token mode: Get started and the theme toggle only", async () => {
      pathname.mockReturnValue("/");
      sameOrigin.value = false;
      renderPlain();
      const { dialog } = await open();
      expect(within(dialog).getAllByRole("link").map((a) => a.textContent)).toEqual(["Get started"]);
      expect(within(dialog).getByRole("link", { name: "Get started" })).toHaveAttribute("href", "/settings");
    });

    it("visitor menu has 44px tap targets for its links; no empty row on token-mode /settings", async () => {
      pathname.mockReturnValue("/");
      sameOrigin.value = true;
      const { unmount } = renderPlain();
      let { dialog } = await open();
      for (const a of within(dialog).getAllByRole("link")) expect(a.className).toContain("min-h-11");
      unmount();
      pathname.mockReturnValue("/settings");
      sameOrigin.value = false;
      renderPlain();
      ({ dialog } = await open());
      expect(within(dialog).queryAllByRole("link")).toHaveLength(0);
      expect(dialog.querySelectorAll("li")).toHaveLength(1); // only the theme toggle row
    });

    it("closes on Escape", async () => {
      pathname.mockReturnValue("/dashboard");
      renderBar();
      const { user } = await open();
      await user.keyboard("{Escape}");
      await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
      expect(screen.getByRole("button", { name: "Menu" })).toHaveAttribute("aria-expanded", "false");
    });

    it("closes when a link is clicked, even a hash link that leaves the pathname unchanged", async () => {
      pathname.mockReturnValue("/settings");
      sameOrigin.value = true;
      renderBar();
      const { user, dialog } = await open();
      await user.click(within(dialog).getByRole("link", { name: "Help" }));
      await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    });

    it("closes when the route changes", async () => {
      pathname.mockReturnValue("/dashboard");
      const { rerender } = renderBar();
      await open();
      pathname.mockReturnValue("/resumes");
      rerender(
        <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
          <TopBar />
        </QueryClientProvider>,
      );
      expect(screen.queryByRole("dialog")).toBeNull();
    });
  });
});

describe("signed-in header", () => {
  it("has exactly two tabs, Dashboard then My resumes, and marks the current one", () => {
    pathname.mockReturnValue("/resumes");
    renderBar();
    const nav = screen.getByRole("navigation", { name: "Primary" });
    expect([...nav.querySelectorAll("a")].map((a) => [a.textContent, a.getAttribute("href")])).toEqual([
      ["Dashboard", "/dashboard"],
      ["My resumes", "/resumes"],
    ]);
    expect(within(nav).getByRole("link", { name: "My resumes" })).toHaveAttribute("aria-current", "page");
    expect(within(nav).getByRole("link", { name: "Dashboard" })).not.toHaveAttribute("aria-current");
  });

  it("maps pages to tabs", () => {
    expect(activeTab("/dashboard")).toBe("/dashboard");
    expect(activeTab("/jobs")).toBe("/dashboard");
    expect(activeTab("/jobs/abc")).toBe("/dashboard");
    expect(activeTab("/resumes")).toBe("/resumes");
    expect(activeTab("/jobs/abc/packages/def")).toBe("/resumes");
    expect(activeTab("/start")).toBeNull();
    expect(activeTab("/profile")).toBeNull();
    expect(activeTab("/settings")).toBeNull();
  });

  it("has no Advanced menu and no Feedback, Jobs, Pipeline, Profile or Tailor tab", () => {
    pathname.mockReturnValue("/dashboard");
    renderBar();
    expect(screen.queryByRole("button", { name: /advanced/i })).toBeNull();
    const nav = screen.getByRole("navigation", { name: "Primary" });
    for (const old of ["Feedback", "Jobs", "Pipeline", "Profile", "Tailor a resume"]) {
      expect(within(nav).queryByRole("link", { name: old })).toBeNull();
    }
  });

  it("has a primary Tailor a resume link (desktop pill and phone +) to /start", () => {
    pathname.mockReturnValue("/dashboard");
    renderBar();
    const links = screen.getAllByRole("link", { name: "Tailor a resume" });
    expect(links).toHaveLength(2);
    for (const a of links) expect(a).toHaveAttribute("href", "/start");
  });

  it("points the logo at /dashboard on every signed-in page, including hosted /settings", () => {
    for (const path of ["/dashboard", "/start", "/settings", "/resumes"]) {
      pathname.mockReturnValue(path);
      const { unmount } = renderBar();
      expect(screen.getByRole("link", { name: "Rhapto" })).toHaveAttribute("href", "/dashboard");
      unmount();
    }
  });

  it("opens an Account disclosure with profile, settings, help, feedback, theme and (hosted) sign out", async () => {
    pathname.mockReturnValue("/dashboard");
    sameOrigin.value = true;
    renderBar();
    const user = userEvent.setup({ delay: null });
    const trigger = await screen.findByRole("button", { name: "Account" });
    expect(trigger).not.toHaveAttribute("role", "menu");
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    await waitFor(() => expect(trigger).toHaveTextContent("M"));
    await user.click(trigger);
    const menu = screen.getByRole("list", { name: "Account" });
    expect([...menu.querySelectorAll("a")].map((a) => [a.textContent, a.getAttribute("href")])).toEqual([
      ["Your profile", "/profile"],
      ["Settings", "/settings"],
      ["Help", "/settings#help"],
      ["Sign out", "/cdn-cgi/access/logout"],
    ]);
    expect(await within(menu).findByRole("button", { name: "Send feedback" })).toBeInTheDocument();
    expect(within(menu).getByRole("button", { name: "Dark mode" })).toBeInTheDocument();
    expect(within(menu).getByText("Sign out")).not.toHaveAttribute("data-link"); // a plain anchor: no router, no prefetch
  });

  it("has no Sign out in token mode", async () => {
    pathname.mockReturnValue("/dashboard");
    sameOrigin.value = false;
    setSettings({ token: "tok", apiUrl: "http://localhost:8000" });
    renderBar("token");
    const user = userEvent.setup({ delay: null });
    await user.click(await screen.findByRole("button", { name: "Account" }));
    expect(screen.queryByText("Sign out")).toBeNull();
  });

  it("Escape closes the disclosure and returns focus to the avatar button", async () => {
    pathname.mockReturnValue("/dashboard");
    renderBar();
    const user = userEvent.setup({ delay: null });
    const trigger = await screen.findByRole("button", { name: "Account" });
    await user.click(trigger);
    // Move focus INTO the panel first. A click leaves focus on the trigger already, so without this the
    // assertion below would pass even if the implementation never restored focus.
    await user.tab();
    expect(screen.getByRole("link", { name: "Your profile" })).toHaveFocus();
    await user.keyboard("{Escape}");
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    expect(trigger).toHaveFocus();
  });

  it("tabbing out of the panel closes it", async () => {
    pathname.mockReturnValue("/dashboard");
    sameOrigin.value = true;
    renderBar();
    const user = userEvent.setup({ delay: null });
    const trigger = await screen.findByRole("button", { name: "Account" });
    await user.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "true");
    await screen.findByRole("button", { name: "Send feedback" });
    for (let i = 0; i < 12 && trigger.getAttribute("aria-expanded") === "true"; i++) await user.tab();
    expect(trigger).toHaveAttribute("aria-expanded", "false");
  });

  it("a blur with a null relatedTarget (Safari/Firefox button click) keeps the panel open", async () => {
    pathname.mockReturnValue("/dashboard");
    renderBar();
    const user = userEvent.setup({ delay: null });
    const trigger = await screen.findByRole("button", { name: "Account" });
    await user.click(trigger);
    const send = await screen.findByRole("button", { name: "Send feedback" });
    fireEvent.blur(send, { relatedTarget: null });
    expect(trigger).toHaveAttribute("aria-expanded", "true");
    await user.click(send);
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
  });

  it("a blur to an element outside the panel closes it", async () => {
    pathname.mockReturnValue("/dashboard");
    renderBar();
    const user = userEvent.setup({ delay: null });
    const trigger = await screen.findByRole("button", { name: "Account" });
    await user.click(trigger);
    const send = await screen.findByRole("button", { name: "Send feedback" });
    fireEvent.blur(send, { relatedTarget: document.body });
    expect(trigger).toHaveAttribute("aria-expanded", "false");
  });

  it("returns focus to Account when the feedback dialog closes", async () => {
    pathname.mockReturnValue("/dashboard");
    renderBar();
    const user = userEvent.setup({ delay: null });
    const trigger = await screen.findByRole("button", { name: "Account" });
    await user.click(trigger);
    await user.click(await screen.findByRole("button", { name: "Send feedback" }));
    await screen.findByRole("dialog");
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    await waitFor(() => expect(trigger).toHaveFocus());
  });

  it("Send feedback closes the menu and opens the dialog, which stays open", async () => {
    pathname.mockReturnValue("/dashboard");
    renderBar();
    const user = userEvent.setup({ delay: null });
    await user.click(await screen.findByRole("button", { name: "Account" }));
    await user.click(await screen.findByRole("button", { name: "Send feedback" }));
    expect(screen.queryByRole("list", { name: "Account" })).toBeNull();
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("offers no Send feedback when /me is refused (signed in at Cloudflare, not on the allowlist)", async () => {
    pathname.mockReturnValue("/dashboard");
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ detail: "forbidden" }), { status: 403, headers: { "content-type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <TopBar />
      </QueryClientProvider>,
    );
    const user = userEvent.setup({ delay: null });
    await user.click(await screen.findByRole("button", { name: "Account" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    await new Promise((r) => setTimeout(r, 50)); // let the refusal land so "absent" is not just "not yet loaded"
    expect(screen.queryByRole("button", { name: "Send feedback" })).toBeNull();
  });

  it("fixes the feedback area and job at open time", async () => {
    const JOB = "11111111-1111-4111-8111-111111111111";
    pathname.mockReturnValue(`/jobs/${JOB}`);
    const posts: unknown[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = input instanceof Request ? input.url : String(input);
        if (url.endsWith("/api/v1/feedback")) {
          const text = input instanceof Request ? await input.clone().text() : String(init?.body ?? "");
          posts.push(JSON.parse(text));
          return new Response(JSON.stringify({ id: "22222222-2222-4222-8222-222222222222", created_at: "2026-10-01T00:00:00Z" }), {
            status: 201,
            headers: { "content-type": "application/json" },
          });
        }
        return new Response(JSON.stringify({ auth_mode: "access", email: "maya@example.com", llm_configured: true, user_id: "11111111-1111-4111-8111-111111111111" }), {
          status: 200,
          headers: { "content-type": "application/json" },
        });
      }),
    );
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const tree = (
      <QueryClientProvider client={client}>
        <TopBar />
      </QueryClientProvider>
    );
    const { rerender } = render(tree);
    const user = userEvent.setup({ delay: null });
    await user.click(await screen.findByRole("button", { name: "Account" }));
    await user.click(await screen.findByRole("button", { name: "Send feedback" }));
    await screen.findByRole("dialog");
    // Navigate while the dialog is open: it must keep the target it opened with.
    pathname.mockReturnValue("/resumes");
    rerender(tree);
    await user.click(screen.getByRole("radio", { name: /it worked well/i }));
    await user.click(screen.getByRole("button", { name: /send/i }));
    await waitFor(() => expect(posts).toHaveLength(1));
    expect(posts[0]).toMatchObject({ form: "quick", job_id: JOB });
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());

    // A second open is tagged for the new page.
    await user.click(await screen.findByRole("button", { name: "Account" }));
    await user.click(await screen.findByRole("button", { name: "Send feedback" }));
    await user.click(await screen.findByRole("radio", { name: /it worked well/i }));
    await user.click(screen.getByRole("button", { name: /send/i }));
    await waitFor(() => expect(posts).toHaveLength(2));
    expect(posts[1]).not.toHaveProperty("job_id");
    expect((posts[1] as { page_area: string }).page_area).not.toBe((posts[0] as { page_area: string }).page_area);
  });

  it("hides Send feedback on the feedback page itself", async () => {
    pathname.mockReturnValue("/feedback");
    renderBar();
    const user = userEvent.setup({ delay: null });
    await user.click(await screen.findByRole("button", { name: "Account" }));
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.queryByRole("button", { name: "Send feedback" })).toBeNull();
  });

  it("is one row: nav, pill and avatar hidden below md; + and Menu hidden from md; 44px targets", () => {
    pathname.mockReturnValue("/dashboard");
    renderBar();
    expect(screen.getByRole("navigation", { name: "Primary" }).className).toEqual(expect.stringContaining("hidden"));
    const menu = screen.getByRole("button", { name: "Menu" });
    expect(menu.className).toContain("md:hidden");
    expect(menu.className).toContain("size-11");
    const [pill, plus] = screen.getAllByRole("link", { name: "Tailor a resume" });
    expect(pill!.className).toContain("hidden");
    expect(plus!.className).toContain("md:hidden");
    expect(plus!.className).toContain("size-11");
    expect(screen.getByRole("button", { name: "Account" }).parentElement!.className).toContain("hidden");
    expect(screen.getByRole("button", { name: "Account" }).className).toContain("size-11");
    expect(screen.getByRole("link", { name: "Rhapto" }).className).toContain("min-h-11");
    expect(screen.getByRole("banner").firstElementChild!.className).not.toContain("flex-wrap");
  });

  describe("phone sheet", () => {
    it("groups Dashboard, My resumes / Your profile, Settings, Help, Send feedback, Theme, Sign out", async () => {
      pathname.mockReturnValue("/dashboard");
      sameOrigin.value = true;
      renderBar();
      const user = userEvent.setup({ delay: null });
      await user.click(screen.getByRole("button", { name: "Menu" }));
      const dialog = await screen.findByRole("dialog", { name: "Menu" });
      expect(within(dialog).getAllByRole("link").map((a) => [a.textContent, a.getAttribute("href")])).toEqual([
        ["Dashboard", "/dashboard"],
        ["My resumes", "/resumes"],
        ["Your profile", "/profile"],
        ["Settings", "/settings"],
        ["Help", "/settings#help"],
        ["Sign out", "/cdn-cgi/access/logout"],
      ]);
      expect(within(dialog).getByText("Account")).toBeInTheDocument();
      expect(await within(dialog).findByRole("button", { name: "Send feedback" })).toBeInTheDocument();
      expect(within(dialog).getByRole("button", { name: "Dark mode" })).toBeInTheDocument();
      expect(within(dialog).getByRole("link", { name: "Dashboard" })).toHaveAttribute("aria-current", "page");
      for (const a of within(dialog).getAllByRole("link")) expect(a.className).toContain("min-h-11");
    });

    it("Send feedback closes the sheet and opens the dialog", async () => {
      pathname.mockReturnValue("/dashboard");
      renderBar();
      const user = userEvent.setup({ delay: null });
      await user.click(screen.getByRole("button", { name: "Menu" }));
      const sheet = await screen.findByRole("dialog", { name: "Menu" });
      await user.click(await within(sheet).findByRole("button", { name: "Send feedback" }));
      await waitFor(() => expect(screen.queryByRole("dialog", { name: "Menu" })).toBeNull());
      expect(await screen.findByRole("dialog")).toBeInTheDocument();
    });
  });
});

afterEach(() => {
  sameOrigin.value = true;
  vi.unstubAllGlobals();
  window.localStorage.clear();
});
