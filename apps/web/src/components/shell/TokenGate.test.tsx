import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { hydrateRoot } from "react-dom/client";
import { renderToString } from "react-dom/server";
import { TokenGate } from "./TokenGate";
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

  it("answers 'what is this?' at the root rather than demanding a token", () => {
    // The root is the one route a stranger reaches without being sent there. A bearer-token field
    // is a dead end for someone who has never heard of Rhapto.
    pathname.current = "/";
    renderGate(<TokenGate><p>secret content</p></TokenGate>);
    expect(screen.queryByText("secret content")).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "Every application, stitched to fit.",
    );
    expect(screen.getByRole("link", { name: /get started/i })).toHaveAttribute("href", "/settings");
  });

  it("always renders the settings page", () => {
    pathname.current = "/settings";
    renderGate(<TokenGate><p>settings form</p></TokenGate>);
    expect(screen.getByText("settings form")).toBeInTheDocument();
  });

  it("renders children once a token is stored", () => {
    pathname.current = "/";
    setSettings({ token: "tok", apiUrl: "http://localhost:8000" });
    renderGate(<TokenGate><p>secret content</p></TokenGate>);
    expect(screen.getByText("secret content")).toBeInTheDocument();
  });

  it("never shows the gate during hydration for a connected user", async () => {
    pathname.current = "/";
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
    await act(async () => {
      hydrateRoot(container, gate);
    });
    expect(container.textContent).toContain("secret content");
    expect(container.textContent).not.toContain("Connect to your Rhapto API");
    container.remove();
  });

  it("reveals children when settings change in the same tab", () => {
    pathname.current = "/";
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
  // route a stranger actually reaches without being sent there (see the "answers 'what is this?'"
  // test above). Duplicated here so mounting <Bootstrapper /> beside <Landing /> can't slip back in
  // unnoticed the way it did in review (verified: it left every other test in this file green).
  it("never fires the bootstrap mutation at / (the anonymous landing page) in token mode", () => {
    pathname.current = "/";
    renderGate(<TokenGate><p>secret content</p></TokenGate>);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "Every application, stitched to fit.",
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

  it("always enables /me, regardless of any stored token", () => {
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
