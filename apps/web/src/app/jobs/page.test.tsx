import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import JobsPage from "./page";

const run = vi.fn();
const saveSearch = vi.fn().mockResolvedValue({ id: "s1", name: "pm" });
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => "/jobs",
}));
vi.mock("@/lib/api/queries", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/queries")>()),
  useLiveSearch: () => ({ run, jobs: [], perSource: null, status: "idle", error: null }),
  useJobsQuery: () => ({ data: [], isLoading: false, error: null }),
  useTracks: () => ({ data: [{ id: "t1", name: "Data PM", min_fit: 60 }] }),
  useTaxonomy: () => ({ data: { fields: [{ id: "engineering", name: "Engineering", roles: [] }] } }),
  useSourceSettings: () => ({ data: [{ source: "themuse", label: "The Muse", enabled: true, needs_key: false, key_set: false }] }),
  useSavedSearches: () => ({ data: [] }),
  useSaveSearch: () => ({ mutateAsync: saveSearch, isPending: false }),
}));

describe("Jobs page", () => {
  it("puts the search form in a mint band and runs a live search", async () => {
    const user = userEvent.setup({ delay: null });
    render(<JobsPage />);
    expect(screen.getByTestId("hero-band").className).toContain("bg-band-mint");
    await user.type(screen.getByLabelText("Title"), "pm");
    await user.click(screen.getByRole("button", { name: "Search" }));
    expect(run).toHaveBeenCalledWith(expect.objectContaining({ query: "pm" }));
  });

  it("offers sort, Show hidden and Save this search", async () => {
    const user = userEvent.setup({ delay: null });
    render(<JobsPage />);
    expect(screen.getByLabelText("Sort")).toBeInTheDocument();
    expect(screen.getByRole("switch", { name: /show hidden/i })).toBeInTheDocument();
    await user.type(screen.getByLabelText("Title"), "pm");
    await user.click(screen.getByRole("button", { name: /save this search/i }));
    expect(saveSearch).toHaveBeenCalledWith(expect.objectContaining({ query: "pm" }));
  });

  it("says the grid is empty rather than showing nothing", () => {
    render(<JobsPage />);
    expect(screen.getByText(/no jobs yet/i)).toBeInTheDocument();
  });
});
