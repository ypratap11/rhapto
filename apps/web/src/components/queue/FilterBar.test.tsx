import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { FilterBar } from "./FilterBar";

const base = { search: "", track: null, tab: "new" as const, region: "us" as const, sort: "fit" as const };

describe("FilterBar", () => {
  it("switches tabs and sort and picks a track", async () => {
    const onChange = vi.fn();
    render(<FilterBar filters={base} onChange={onChange} tracks={[{ id: "data-pm", name: "Data PM" }]} />);
    const user = userEvent.setup({ delay: null });
    await user.click(screen.getByRole("tab", { name: /tailored/i }));
    expect(onChange).toHaveBeenLastCalledWith({ ...base, tab: "tailored" });
    await user.click(screen.getByRole("button", { name: /newest/i }));
    expect(onChange).toHaveBeenLastCalledWith({ ...base, sort: "newest" });
    expect(screen.getByLabelText(/track/i)).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /^new$/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /low fit/i })).toBeInTheDocument();
  });

  it("shows the current region and narrows to the preferred area", async () => {
    const onChange = vi.fn();
    render(<FilterBar filters={base} onChange={onChange} tracks={[]} />);
    const region = screen.getByLabelText("Region");
    expect(region).toHaveTextContent("US and remote");
    const user = userEvent.setup({ delay: null });
    await user.click(region);
    await user.click(await screen.findByRole("option", { name: "Preferred area" }));
    expect(onChange).toHaveBeenLastCalledWith({ ...base, region: "preferred" });
  });

  it("widens to anywhere", async () => {
    const onChange = vi.fn();
    render(<FilterBar filters={{ ...base, region: "preferred" }} onChange={onChange} tracks={[]} />);
    const user = userEvent.setup({ delay: null });
    await user.click(screen.getByLabelText("Region"));
    await user.click(await screen.findByRole("option", { name: "Anywhere" }));
    expect(onChange).toHaveBeenLastCalledWith({ ...base, region: "any" });
  });
});
