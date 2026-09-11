import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

const mutateAsync = vi.fn().mockResolvedValue([]);
vi.mock("@/lib/api/queries", () => ({
  useAggregators: () => ({ isLoading: false, error: null, data: [{ source: "remoteok", enabled: true, keywords: ["pm"] }] }),
  usePutAggregators: () => ({ mutateAsync, isPending: false }),
  useSources: () => ({ data: [{ name: "remoteok", kind: "aggregator", label: "RemoteOK", needs_board: false }, { name: "hn-hiring", kind: "aggregator", label: "Hacker News Who's Hiring", needs_board: false }, { name: "greenhouse", kind: "board", label: "Greenhouse", needs_board: true }] }),
}));

import { AggregatorsSection } from "./AggregatorsSection";

describe("AggregatorsSection", () => {
  it("renders one switch per aggregator and saves the full list", async () => {
    render(<AggregatorsSection />);
    const user = userEvent.setup({ delay: null });
    expect(screen.getByLabelText("RemoteOK")).toBeChecked();
    expect(screen.getByLabelText("Hacker News Who's Hiring")).not.toBeChecked();
    await user.click(screen.getByLabelText("Hacker News Who's Hiring"));
    await user.click(screen.getByRole("button", { name: /save/i }));
    expect(mutateAsync).toHaveBeenCalledWith([
      { source: "remoteok", enabled: true, keywords: ["pm"] },
      { source: "hn-hiring", enabled: true, keywords: ["pm"] },
    ]);
  });
});
