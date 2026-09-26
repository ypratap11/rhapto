import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { hydrateRoot } from "react-dom/client";
import { renderToString } from "react-dom/server";
import { TokenGate } from "./TokenGate";
import { setSettings } from "@/lib/api/client";
import { useMe } from "@/lib/api/queries";

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
vi.mock("@/lib/api/queries", () => ({ useMe: vi.fn(() => ({ isPending: true, isSuccess: false })) }));

function renderGate(children: React.ReactNode) {
  const client = new QueryClient();
  return render(<QueryClientProvider client={client}>{children}</QueryClientProvider>);
}

afterEach(() => window.localStorage.clear());

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
});

describe("TokenGate in access mode", () => {
  beforeEach(() => {
    sameOriginFlag.value = true;
  });
  afterEach(() => {
    sameOriginFlag.value = false;
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

  it("refuses access when /me fails (not on the invite list), never showing the token-mode card", () => {
    vi.mocked(useMe).mockReturnValue({ isPending: false, isSuccess: false } as ReturnType<typeof useMe>);
    pathname.current = "/jobs";
    renderGate(<TokenGate><p>secret content</p></TokenGate>);
    expect(screen.queryByText("secret content")).not.toBeInTheDocument();
    expect(screen.getByText(/invite-only/i)).toBeInTheDocument();
    expect(screen.queryByText(/Connect to your Rhapto API/i)).not.toBeInTheDocument();
  });
});
