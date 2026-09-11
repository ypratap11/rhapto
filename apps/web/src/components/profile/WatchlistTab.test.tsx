import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

const putWatchlist = vi.fn().mockResolvedValue([]);
const putAggregators = vi.fn().mockResolvedValue([]);
vi.mock("@/lib/api/queries", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/queries")>()),
  useWatchlist: () => ({
    data: [{ company: "Acme", source: "greenhouse", board: "acme", keywords: ["etl"] }],
    isLoading: false,
    error: null,
  }),
  usePutWatchlist: () => ({ mutateAsync: putWatchlist, isPending: false }),
  useAggregators: () => ({ data: [], isLoading: false, error: null }),
  usePutAggregators: () => ({ mutateAsync: putAggregators, isPending: false }),
  useSources: () => ({
    isLoading: false,
    error: null,
    data: [
      { name: "greenhouse", kind: "board", label: "Greenhouse", needs_board: true },
      { name: "lever", kind: "board", label: "Lever", needs_board: true },
      { name: "ashby", kind: "board", label: "Ashby", needs_board: true },
      { name: "remoteok", kind: "aggregator", label: "RemoteOK", needs_board: false },
      { name: "hn-hiring", kind: "aggregator", label: "Hacker News Who's Hiring", needs_board: false },
    ],
  }),
}));

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { WatchlistTab } from "./WatchlistTab";

describe("WatchlistTab", () => {
  it("shows the watchlist entry's keywords and appends a typed keyword on save", async () => {
    render(<WatchlistTab />);
    const user = userEvent.setup({ delay: null });
    const keywordsInput = screen.getByLabelText("Keywords 1") as HTMLInputElement;
    expect(keywordsInput.value).toBe("etl");
    await user.type(keywordsInput, ", pm");
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(putWatchlist).toHaveBeenCalledWith([expect.objectContaining({ company: "Acme", keywords: ["etl", "pm"] })]);
  });

  it("lists no-adapter board sources with a suffix", async () => {
    render(<WatchlistTab />);
    const user = userEvent.setup({ delay: null });
    await user.click(screen.getByRole("combobox", { name: "Source 1" }));
    expect(await screen.findByText("smartrecruiters (no adapter yet)")).toBeInTheDocument();
    expect(screen.getByText("workable (no adapter yet)")).toBeInTheDocument();
  });
});
