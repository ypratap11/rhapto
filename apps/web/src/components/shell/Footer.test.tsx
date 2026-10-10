import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ACCESS_REQUEST_MAILTO, ACCESS_REQUEST_URL } from "@/components/landing/access";
import { setSettings } from "@/lib/api/client";
import { GITHUB_URL } from "@/lib/links";
import { Footer } from "./Footer";

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
const pathname = vi.fn(() => "/");
vi.mock("next/navigation", () => ({ usePathname: () => pathname() }));

afterEach(() => {
  sameOrigin.value = true;
  window.localStorage.clear();
});

const footerLinks = () => [...screen.getByRole("contentinfo").querySelectorAll("a")];
const names = () => footerLinks().map((a) => a.textContent);

describe("Footer", () => {
  it("the repo link is the public GitHub repo", () => {
    expect(GITHUB_URL).toBe("https://github.com/ypratap11/rhapto");
  });

  it("hosted / (visitor): Open source, Request beta access, no Feedback, copyright", () => {
    pathname.mockReturnValue("/");
    render(<Footer />);
    expect(names()).toEqual(["Open source", "Request beta access"]);
    expect(screen.getByRole("link", { name: "Open source" })).toHaveAttribute("href", GITHUB_URL);
    expect(screen.getByRole("link", { name: "Request beta access" })).toHaveAttribute("href", ACCESS_REQUEST_URL || ACCESS_REQUEST_MAILTO);
    expect(screen.getByText("© 2026 Rhapto")).toBeInTheDocument();
  });

  it("token mode / : Open source only (no request link, no Feedback)", () => {
    sameOrigin.value = false;
    pathname.mockReturnValue("/");
    render(<Footer />);
    expect(names()).toEqual(["Open source"]);
  });

  it("hosted in-app (/start and /settings): Feedback -> /feedback appears", () => {
    for (const path of ["/start", "/settings"]) {
      pathname.mockReturnValue(path);
      const { unmount } = render(<Footer />);
      expect(screen.getByRole("link", { name: "Feedback" })).toHaveAttribute("href", "/feedback");
      unmount();
    }
  });

  it("token-mode /settings: Feedback only once a token is stored (same predicate as the header)", () => {
    sameOrigin.value = false;
    pathname.mockReturnValue("/settings");
    const { unmount } = render(<Footer />);
    expect(screen.queryByRole("link", { name: "Feedback" })).toBeNull();
    unmount();
    setSettings({ token: "tok", apiUrl: "http://localhost:8000" });
    render(<Footer />);
    expect(screen.getByRole("link", { name: "Feedback" })).toBeInTheDocument();
  });

  it("is centred on phones and has 44px phone targets", () => {
    render(<Footer />);
    expect(screen.getByRole("contentinfo").firstElementChild!.className).toContain("justify-center");
    for (const a of footerLinks()) expect(a.className).toContain("max-md:min-h-11");
  });
});
