import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { hydrateRoot } from "react-dom/client";
import { renderToString } from "react-dom/server";
import { TokenGate } from "./TokenGate";
import { setSettings } from "@/lib/api/client";

const pathname = { current: "/" };
vi.mock("next/navigation", () => ({ usePathname: () => pathname.current }));

afterEach(() => window.localStorage.clear());

describe("TokenGate", () => {
  it("blocks content without a token and links to settings", () => {
    pathname.current = "/jobs";
    render(<TokenGate><p>secret content</p></TokenGate>);
    expect(screen.queryByText("secret content")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /open settings/i })).toHaveAttribute("href", "/settings");
  });

  it("answers 'what is this?' at the root rather than demanding a token", () => {
    // The root is the one route a stranger reaches without being sent there. A bearer-token field
    // is a dead end for someone who has never heard of Rhapto.
    pathname.current = "/";
    render(<TokenGate><p>secret content</p></TokenGate>);
    expect(screen.queryByText("secret content")).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "Every application, stitched to fit.",
    );
    expect(screen.getByRole("link", { name: /get started/i })).toHaveAttribute("href", "/settings");
  });

  it("always renders the settings page", () => {
    pathname.current = "/settings";
    render(<TokenGate><p>settings form</p></TokenGate>);
    expect(screen.getByText("settings form")).toBeInTheDocument();
  });

  it("renders children once a token is stored", () => {
    pathname.current = "/";
    setSettings({ token: "tok", apiUrl: "http://localhost:8000" });
    render(<TokenGate><p>secret content</p></TokenGate>);
    expect(screen.getByText("secret content")).toBeInTheDocument();
  });

  it("never shows the gate during hydration for a connected user", async () => {
    pathname.current = "/";
    setSettings({ token: "tok", apiUrl: "http://localhost:8000" });
    const html = renderToString(<TokenGate><p>secret content</p></TokenGate>);
    expect(html).not.toMatch(/Connect to your Rhapto API/);
    const container = document.createElement("div");
    container.innerHTML = html;
    document.body.appendChild(container);
    await act(async () => {
      hydrateRoot(container, <TokenGate><p>secret content</p></TokenGate>);
    });
    expect(container.textContent).toContain("secret content");
    expect(container.textContent).not.toContain("Connect to your Rhapto API");
    container.remove();
  });

  it("reveals children when settings change in the same tab", () => {
    pathname.current = "/";
    render(<TokenGate><p>secret content</p></TokenGate>);
    expect(screen.queryByText("secret content")).not.toBeInTheDocument();
    act(() => {
      setSettings({ token: "tok", apiUrl: "http://localhost:8000" });
    });
    expect(screen.getByText("secret content")).toBeInTheDocument();
  });
});
