import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const searchParams = { current: new URLSearchParams() };
const replace = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
  useSearchParams: () => searchParams.current,
}));

vi.mock("@/lib/api/queries", () => ({
  usePackageList: () => ({ data: [], isLoading: false, error: null }),
  useTracks: () => ({ data: [] }),
}));

import PackagesPage from "./page";

describe("PackagesPage", () => {
  it("selects the Blocked chip for ?filter=blocked", () => {
    searchParams.current = new URLSearchParams("filter=blocked");
    render(<PackagesPage />);
    expect(screen.getByRole("tab", { name: /blocked/i })).toHaveAttribute("aria-selected", "true");
  });

  it("falls back to the review filter for an invalid ?filter value", () => {
    searchParams.current = new URLSearchParams("filter=bogus");
    render(<PackagesPage />);
    expect(screen.getByRole("tab", { name: /needs review/i })).toHaveAttribute("aria-selected", "true");
  });
});
