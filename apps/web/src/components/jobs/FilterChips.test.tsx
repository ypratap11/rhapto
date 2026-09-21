import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { DEFAULT_SEARCH_STATE } from "@/lib/search-state";
import { FilterChips } from "./FilterChips";

const sources = [{ source: "themuse", label: "The Muse" }, { source: "adzuna", label: "Adzuna" }];

describe("FilterChips", () => {
  it("offers the spec's date, source and fit values and reports a choice", async () => {
    const user = userEvent.setup({ delay: null });
    const onChange = vi.fn();
    render(<FilterChips value={DEFAULT_SEARCH_STATE} onChange={onChange} sources={sources} />);

    for (const label of ["24h", "7d", "30d", "90d", "Any time", "75+", "60+", "All fits", "The Muse", "Adzuna"]) {
      expect(screen.getByRole("button", { name: label })).toBeInTheDocument();
    }
    expect(screen.getByRole("button", { name: "90d" })).toHaveAttribute("aria-pressed", "true");

    await user.click(screen.getByRole("button", { name: "7d" }));
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ posted_within: "7d" }));
    await user.click(screen.getByRole("button", { name: "Adzuna" }));
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ sources: ["adzuna"] }));
  });
});
