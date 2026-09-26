import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { TopBar } from "./TopBar";

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

  it("points the Dashboard tab at /dashboard and marks it current there but not at /", () => {
    pathname.mockReturnValue("/dashboard");
    render(<TopBar />);
    expect(screen.getByRole("link", { name: "Dashboard" })).toHaveAttribute("href", "/dashboard");
    expect(screen.getByRole("link", { name: "Dashboard" })).toHaveAttribute("aria-current", "page");

    pathname.mockReturnValue("/");
    render(<TopBar />);
    expect(screen.getAllByRole("link", { name: "Dashboard" }).pop()).not.toHaveAttribute("aria-current");
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
});
