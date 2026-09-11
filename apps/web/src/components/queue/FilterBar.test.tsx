import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { FilterBar } from "./FilterBar";

const base = { search: "", track: null, bucket: "fit" as const, sort: "fit" as const };

describe("FilterBar", () => {
  it("toggles bucket and sort and picks a track", async () => {
    const onChange = vi.fn();
    render(<FilterBar filters={base} onChange={onChange} tracks={[{ id: "data-pm", name: "Data PM" }]} />);
    const user = userEvent.setup({ delay: null });
    await user.click(screen.getByRole("button", { name: /low fit/i }));
    expect(onChange).toHaveBeenLastCalledWith({ ...base, bucket: "low" });
    await user.click(screen.getByRole("button", { name: /newest/i }));
    expect(onChange).toHaveBeenLastCalledWith({ ...base, sort: "newest" });
    expect(screen.getByLabelText(/track/i)).toBeInTheDocument();
  });
});
