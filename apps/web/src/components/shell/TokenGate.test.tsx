import { render, renderHook, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { hydrateRoot } from "react-dom/client";
import { renderToString } from "react-dom/server";
import { TokenGate, useSignedIn } from "./TokenGate";
import { Landing } from "@/components/landing/Landing";
import { ApiError, setSettings } from "@/lib/api/client";
import { useBootstrap, useMe } from "@/lib/api/queries";

const pathname = { current: "/" };
vi.mock("next/navigation", () => ({ usePathname: () => pathname.current }));

const sameOriginFlag = { value: false };
vi.mock("@/lib/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/client")>();
  return {
    ...actual,
    get SAME_ORIGIN_DEPLOYMENT() {
      return sameOriginFlag.value;
    },
  };
});
// Fix-round I7: a fresh `vi.fn()` per `useBootstrap()` call (the original mock) made it impossible
// to assert whether Bootstrapper ever actually called `.mutate()` -- every test saw a brand-new
// spy. Hoisting one shared spy (name prefixed `mock` so Vitest's hoisting transform can see it
// inside the `vi.mock` factory below) lets tests assert on it directly.
const mockBootstrapMutate = vi.fn();
vi.mock("@/lib/api/queries", () => ({
  useMe: vi.fn(() => ({ isPending: true, isSuccess: false })),
  useBootstrap: vi.fn(() => ({ isIdle: true, mutate: mockBootstrapMutate })),
}));

function renderGate(children: React.ReactNode) {
  const client = new QueryClient();
  return render(<QueryClientProvider client={client}>{children}</QueryClientProvider>);
}

afterEach(() => {
  window.localStorage.clear();
  // Bootstrapper's fix-round M1 sessionStorage latch must not leak between tests, or every test
  // after the first one that mounts Bootstrapper would see "already attempted" and never fire.
  window.sessionStorage.clear();
  mockBootstrapMutate.mockClear();
});

describe("TokenGate", () => {
  it("blocks content without a token and links to settings", () => {
    pathname.current = "/jobs";
    renderGate(<TokenGate><p>secret content</p></TokenGate>);
    expect(screen.queryByText("secret content")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /open settings/i })).toHaveAttribute("href", "/settings");
  });

  // Landing-default task: "/" is now in PUBLIC_ROUTES, so TokenGate no longer substitutes its own
  // fallback there (that used to be how a stranger at "/" saw the pitch instead of a bearer-token
  // field). It just renders children -- app/page.tsx is what supplies <Landing/> as those children
  // in production. This is the test that pins the owner's actual request: before this task, an
  // anonymous "/" visit in token mode was blocked behind the same Connect card as every other route.
  it("renders its children at / with no token present, in token mode", () => {
    pathname.current = "/";
    renderGate(<TokenGate><p>secret content</p></TokenGate>);
    expect(screen.getByText("secret content")).toBeInTheDocument();
    expect(screen.queryByText(/connect to your rhapto api/i)).not.toBeInTheDocument();
  });

  it("always renders the settings page", () => {
    pathname.current = "/settings";
    renderGate(<TokenGate><p>settings form</p></TokenGate>);
    expect(screen.getByText("settings form")).toBeInTheDocument();
  });

  it("renders children once a token is stored", () => {
    // "/jobs", not "/": "/" is a PUBLIC_ROUTE now and renders children with or without a token,
    // which would not exercise the token-gating this test is for (review finding C2).
    pathname.current = "/jobs";
    setSettings({ token: "tok", apiUrl: "http://localhost:8000" });
    renderGate(<TokenGate><p>secret content</p></TokenGate>);
    expect(screen.getByText("secret content")).toBeInTheDocument();
  });

  it("never shows the gate during hydration for a connected user", async () => {
    // "/jobs", not "/": at a PUBLIC_ROUTE, TokenGate never even reaches the `tokenPresent === null`
    // branch this test pins (SSR/hydration must never flash the Connect card), so "/" would let this
    // pass for the wrong reason — or for no reason (review finding C2, proved by mutating
    // `getServerSnapshot` to return `false`, which left this suite green while "/" was the fixture).
    pathname.current = "/jobs";
    setSettings({ token: "tok", apiUrl: "http://localhost:8000" });
    const client = new QueryClient();
    const gate = (
      <QueryClientProvider client={client}>
        <TokenGate><p>secret content</p></TokenGate>
      </QueryClientProvider>
    );
    const html = renderToString(gate);
    expect(html).not.toMatch(/Connect to your Rhapto API/);
    const container = document.createElement("div");
    container.innerHTML = html;
    document.body.appendChild(container);
    // try/finally: this container is appended by hand, so testing-library's automatic cleanup does
    // not own it. Removing it only on the success path meant a FAILING assertion here leaked the
    // node and poisoned every later `screen` query in this file -- during review that surfaced as a
    // spurious fourth failure, an access-mode test reporting the token-mode Connect card. Harmless
    // while this test could not fail; a real trap now that finding C2 re-armed it.
    try {
      await act(async () => {
        hydrateRoot(container, gate);
      });
      expect(container.textContent).toContain("secret content");
      expect(container.textContent).not.toContain("Connect to your Rhapto API");
    } finally {
      container.remove();
    }
  });

  it("reveals children when settings change in the same tab", () => {
    // "/jobs", not "/": "/" is a PUBLIC_ROUTE now and would show children regardless of token,
    // which would not exercise the reactivity this test is for.
    pathname.current = "/jobs";
    renderGate(<TokenGate><p>secret content</p></TokenGate>);
    expect(screen.queryByText("secret content")).not.toBeInTheDocument();
    act(() => {
      setSettings({ token: "tok", apiUrl: "http://localhost:8000" });
    });
    expect(screen.getByText("secret content")).toBeInTheDocument();
  });

  // --- fix-round finding I4: /me must not fire in token mode until a token exists ---

  it("does not enable /me in token mode until a token is stored", () => {
    pathname.current = "/jobs";
    renderGate(<TokenGate><p>secret content</p></TokenGate>);
    expect(vi.mocked(useMe)).toHaveBeenCalledWith({ enabled: false });
  });

  it("enables /me once a token is stored, in token mode", () => {
    pathname.current = "/jobs";
    setSettings({ token: "tok", apiUrl: "http://localhost:8000" });
    renderGate(<TokenGate><p>secret content</p></TokenGate>);
    expect(vi.mocked(useMe)).toHaveBeenCalledWith({ enabled: true });
  });

  // --- fix-round finding I7: the whole web-side bootstrap wiring was untested, including the
  // exact regression the TokenGate-vs-providers.tsx deviation exists to prevent ---

  it("never fires the bootstrap mutation at /jobs in token mode with no token stored", () => {
    pathname.current = "/jobs";
    renderGate(<TokenGate><p>secret content</p></TokenGate>);
    expect(screen.queryByText("secret content")).not.toBeInTheDocument(); // not signed in
    expect(mockBootstrapMutate).not.toHaveBeenCalled();
  });

  // Plan-review N2: the /jobs case above is route-specific and misses the landing page -- the one
  // route a stranger actually reaches without being sent there. Duplicated here so mounting
  // <Bootstrapper /> beside <Landing /> can't slip back in unnoticed the way it did in review
  // (verified: it left every other test in this file green).
  //
  // Landing-default task: children is <Landing/> here, not the `<p>secret content</p>` stand-in
  // used elsewhere in this file. That stand-in stops being a faithful fixture at "/" once "/"
  // becomes a PUBLIC_ROUTE -- TokenGate now renders whatever children it is given there (see the
  // "renders its children at /" test above) rather than substituting Landing itself, and in
  // production what app/page.tsx actually hands TokenGate as children at "/" is <Landing/>. Both
  // assertions below are unchanged from before this task; only this fixture was updated to match.
  // Review finding M4: the `h1` assertion now proves something different than it did before this
  // task -- it used to prove TokenGate *substitutes* <Landing/> at "/" regardless of children; now
  // it proves the <Landing/> the test itself passed in was rendered (it duplicates the "renders its
  // children at /" test above). Harmless -- the load-bearing check here is `mockBootstrapMutate`,
  // which still discriminates on its own -- but kept for its original purpose: pinning that
  // Bootstrapper never mounts beside a real Landing render, not a stand-in.
  it("never fires the bootstrap mutation at / (the anonymous landing page) in token mode", () => {
    pathname.current = "/";
    renderGate(<TokenGate><Landing /></TokenGate>);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "A resume you can defend in any interview.",
    );
    expect(mockBootstrapMutate).not.toHaveBeenCalled();
  });
});

describe("TokenGate in access mode", () => {
  beforeEach(() => {
    sameOriginFlag.value = true;
  });
  afterEach(() => {
    sameOriginFlag.value = false;
  });

  it("enables /me on a non-public route regardless of any stored token", () => {
    vi.mocked(useMe).mockReturnValue({ isPending: true, isSuccess: false } as ReturnType<typeof useMe>);
    pathname.current = "/jobs";
    renderGate(<TokenGate><p>secret content</p></TokenGate>);
    expect(vi.mocked(useMe)).toHaveBeenCalledWith({ enabled: true });
  });

  it("renders nothing while /me is pending", () => {
    vi.mocked(useMe).mockReturnValue({ isPending: true, isSuccess: false } as ReturnType<typeof useMe>);
    pathname.current = "/jobs";
    const { container } = renderGate(<TokenGate><p>secret content</p></TokenGate>);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders children once /me succeeds, with no token in localStorage", () => {
    vi.mocked(useMe).mockReturnValue({ isPending: false, isSuccess: true } as ReturnType<typeof useMe>);
    pathname.current = "/jobs";
    renderGate(<TokenGate><p>secret content</p></TokenGate>);
    expect(screen.getByText("secret content")).toBeInTheDocument();
  });

  // --- fix-round finding I7 (continued): the positive case, in access mode ---

  it("fires the bootstrap mutation exactly once once /me succeeds", () => {
    vi.mocked(useMe).mockReturnValue({ isPending: false, isSuccess: true } as ReturnType<typeof useMe>);
    pathname.current = "/jobs";
    renderGate(<TokenGate><p>secret content</p></TokenGate>);
    expect(mockBootstrapMutate).toHaveBeenCalledTimes(1);
  });

  // --- fix-round finding M1/M2: a sessionStorage latch, not just `bootstrap.isIdle`, so a
  // signed-in user remounting Bootstrapper (navigation through /settings or /about, or a React
  // StrictMode dev-mode double-invoke) does not re-fire the request every time ---

  it("does not re-fire the bootstrap mutation on a second mount within the same browser session", () => {
    vi.mocked(useMe).mockReturnValue({ isPending: false, isSuccess: true } as ReturnType<typeof useMe>);
    pathname.current = "/jobs";
    const first = renderGate(<TokenGate><p>secret content</p></TokenGate>);
    first.unmount();
    renderGate(<TokenGate><p>secret content</p></TokenGate>);
    expect(mockBootstrapMutate).toHaveBeenCalledTimes(1);
  });

  // --- fix-round finding M6: a bootstrap failure must not present as an authentication failure ---

  it("still renders children when the bootstrap mutation itself errors", () => {
    vi.mocked(useMe).mockReturnValue({ isPending: false, isSuccess: true } as ReturnType<typeof useMe>);
    // mockReturnValueOnce, not mockReturnValue: this must not leak into later tests, which rely on
    // the module mock's default { isIdle: true, ... } shape.
    vi.mocked(useBootstrap).mockReturnValueOnce({
      isIdle: false,
      isError: true,
      error: new ApiError(500, null, "boom"),
      mutate: mockBootstrapMutate,
    } as unknown as ReturnType<typeof useBootstrap>);
    pathname.current = "/jobs";
    renderGate(<TokenGate><p>secret content</p></TokenGate>);
    expect(screen.getByText("secret content")).toBeInTheDocument();
    expect(screen.queryByText(/invite-only/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/could not reach rhapto/i)).not.toBeInTheDocument();
  });

  it("refuses access when /me returns 401/403 (not on the invite list), never showing the token-mode card", () => {
    vi.mocked(useMe).mockReturnValue({
      isPending: false,
      isSuccess: false,
      error: new ApiError(403, null, "Forbidden"),
    } as unknown as ReturnType<typeof useMe>);
    pathname.current = "/jobs";
    renderGate(<TokenGate><p>secret content</p></TokenGate>);
    expect(screen.queryByText("secret content")).not.toBeInTheDocument();
    expect(screen.getByText(/invite-only/i)).toBeInTheDocument();
    expect(screen.queryByText(/Connect to your Rhapto API/i)).not.toBeInTheDocument();
  });

  // --- fix-round finding I1: a 500/network failure is not "you are not invited" ---

  it("shows a generic retry state, not 'invite-only', when /me fails for a reason other than 401/403", () => {
    const refetch = vi.fn();
    vi.mocked(useMe).mockReturnValue({
      isPending: false,
      isSuccess: false,
      error: new ApiError(500, null, "Internal Server Error"),
      refetch,
    } as unknown as ReturnType<typeof useMe>);
    pathname.current = "/jobs";
    renderGate(<TokenGate><p>secret content</p></TokenGate>);
    expect(screen.queryByText("secret content")).not.toBeInTheDocument();
    expect(screen.queryByText(/invite-only/i)).not.toBeInTheDocument();
    expect(screen.getByText(/could not reach rhapto/i)).toBeInTheDocument();
    screen.getByRole("button", { name: /retry/i }).click();
    expect(refetch).toHaveBeenCalledTimes(1);
  });

  it("shows the generic retry state (not 'invite-only') when /me fails with no ApiError at all", () => {
    // A network error (fetch rejecting) never reaches unwrap()'s ApiError construction, so
    // me.error may not be an ApiError instance at all; that must still be treated as "couldn't
    // reach", not silently coerced into either card.
    vi.mocked(useMe).mockReturnValue({
      isPending: false,
      isSuccess: false,
      error: new Error("network error"),
      refetch: vi.fn(),
    } as unknown as ReturnType<typeof useMe>);
    pathname.current = "/jobs";
    renderGate(<TokenGate><p>secret content</p></TokenGate>);
    expect(screen.queryByText(/invite-only/i)).not.toBeInTheDocument();
    expect(screen.getByText(/could not reach rhapto/i)).toBeInTheDocument();
  });

  // Landing-default task, item 4 (access-mode half): PUBLIC_ROUTES is checked before the
  // SAME_ORIGIN_DEPLOYMENT branch (Task 2's fix round moved it there deliberately, so /settings
  // stays reachable too), so "/" renders children even when /me is refused -- there is no wall
  // of "Access refused" for a stranger who has never heard of Rhapto, only for someone who
  // navigates to an app route directly without being let in.
  it("renders its children at / even when /me fails, in access mode", () => {
    vi.mocked(useMe).mockReturnValue({
      isPending: false,
      isSuccess: false,
      error: new ApiError(403, null, "Forbidden"),
    } as unknown as ReturnType<typeof useMe>);
    pathname.current = "/";
    renderGate(<TokenGate><p>secret content</p></TokenGate>);
    expect(screen.getByText("secret content")).toBeInTheDocument();
    expect(screen.queryByText(/invite-only/i)).not.toBeInTheDocument();
    // Review finding I2: "/" must never seed, in the mode that is actually world-readable, not just
    // in token mode (which the pre-existing test at ":157" already pinned).
    expect(mockBootstrapMutate).not.toHaveBeenCalled();
  });

  // Review finding I2 (continued): the live post-bypass configuration is /me *succeeding* at / --
  // nothing covered that /me outcome before. Bootstrapper must still not mount there.
  it("renders its children at / when /me succeeds, in access mode, without ever seeding", () => {
    vi.mocked(useMe).mockReturnValue({ isPending: false, isSuccess: true } as ReturnType<typeof useMe>);
    pathname.current = "/";
    renderGate(<TokenGate><p>secret content</p></TokenGate>);
    expect(screen.getByText("secret content")).toBeInTheDocument();
    expect(mockBootstrapMutate).not.toHaveBeenCalled();
  });

  // Review finding I1: the public-route return (":103") stops `me` being *rendered*, not
  // *requested* -- `enabled` used to stay live in access mode regardless of route, so every view of
  // the world-readable landing page fired a same-origin GET /api/v1/me for nothing (and, for a
  // signed-in visitor, still reached `current_user`, which creates the account row as a side
  // effect). `enabled` must go false the moment the route is public.
  it("does not enable /me at /, in access mode", () => {
    pathname.current = "/";
    renderGate(<TokenGate><p>secret content</p></TokenGate>);
    expect(vi.mocked(useMe)).toHaveBeenCalledWith({ enabled: false });
  });

  // --- fix-round finding I2: /settings must stay reachable in access mode ---

  it("keeps /settings reachable even while /me is refused, so there is a way to fix the configuration", () => {
    vi.mocked(useMe).mockReturnValue({
      isPending: false,
      isSuccess: false,
      error: new ApiError(403, null, "Forbidden"),
    } as unknown as ReturnType<typeof useMe>);
    pathname.current = "/settings";
    renderGate(<TokenGate><p>settings form</p></TokenGate>);
    expect(screen.getByText("settings form")).toBeInTheDocument();
  });
});

describe("useSignedIn", () => {
  afterEach(() => {
    sameOriginFlag.value = false;
  });

  it.each(["/", "/about", "/settings"])("is false on the public route %s, even with a token stored", (path) => {
    pathname.current = path;
    setSettings({ token: "tok", apiUrl: "http://localhost:8000" });
    expect(renderHook(() => useSignedIn()).result.current).toBe(false);
  });

  it.each(["/", "/about", "/settings"])("is false on the public route %s in access mode", (path) => {
    sameOriginFlag.value = true;
    pathname.current = path;
    expect(renderHook(() => useSignedIn()).result.current).toBe(false);
  });

  it("is true on an app route with a token (token mode) and false without one", () => {
    pathname.current = "/dashboard";
    expect(renderHook(() => useSignedIn()).result.current).toBe(false);
    setSettings({ token: "tok", apiUrl: "http://localhost:8000" });
    expect(renderHook(() => useSignedIn()).result.current).toBe(true);
  });

  it("is true on an app route in access mode with no token", () => {
    sameOriginFlag.value = true;
    pathname.current = "/dashboard";
    expect(renderHook(() => useSignedIn()).result.current).toBe(true);
  });

  // The survey is an app page behind sign-in, not a public route: /feedback must never be added to
  // PUBLIC_ROUTES (that would also open it, client-side, to a visitor with no session).
  it("treats /feedback as a signed-in-only route", () => {
    pathname.current = "/feedback";
    expect(renderHook(() => useSignedIn()).result.current).toBe(false);
    setSettings({ token: "tok", apiUrl: "http://localhost:8000" });
    expect(renderHook(() => useSignedIn()).result.current).toBe(true);
  });
});
