import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { DEFAULT_SEARCH_STATE } from "@/lib/search-state";
import { SearchForm } from "./SearchForm";

const fields = [{ id: "engineering", name: "Engineering" }, { id: "design", name: "Design" }];

describe("SearchForm", () => {
  it("submits the typed title and location", async () => {
    const user = userEvent.setup({ delay: null });
    const onSubmit = vi.fn();
    const onChange = vi.fn();
    render(<SearchForm value={{ ...DEFAULT_SEARCH_STATE, location: "Austin, TX" }} onChange={onChange} onSubmit={onSubmit} fields={fields} pending={false} />);

    await user.type(screen.getByLabelText("Title"), "program manager");
    expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ query: expect.stringContaining("r") }));
    expect(screen.getByLabelText("Location")).toHaveValue("Austin, TX");
    await user.click(screen.getByRole("button", { name: "Search" }));
    expect(onSubmit).toHaveBeenCalledTimes(1);
  });

  it("shows My tracks as the default field", () => {
    render(<SearchForm value={DEFAULT_SEARCH_STATE} onChange={vi.fn()} onSubmit={vi.fn()} fields={fields} pending={false} />);
    expect(screen.getByLabelText("Field")).toHaveTextContent("My tracks");
  });
});
