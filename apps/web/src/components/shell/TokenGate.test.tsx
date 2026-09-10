import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { TokenGate } from "./TokenGate";
import { setSettings } from "@/lib/api/client";

const pathname = { current: "/" };
vi.mock("next/navigation", () => ({ usePathname: () => pathname.current }));

afterEach(() => window.localStorage.clear());

describe("TokenGate", () => {
  it("blocks content without a token and links to settings", () => {
    pathname.current = "/";
    render(<TokenGate><p>secret content</p></TokenGate>);
    expect(screen.queryByText("secret content")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /open settings/i })).toHaveAttribute("href", "/settings");
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
});
