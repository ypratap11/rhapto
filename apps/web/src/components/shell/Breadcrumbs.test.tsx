import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Breadcrumbs } from "./Breadcrumbs";

describe("Breadcrumbs", () => {
  it("links every segment but the last and sets the document title to match", () => {
    render(<Breadcrumbs items={[{ label: "Jobs", href: "/jobs" }, { label: "Scale AI · Technical Program Manager" }]} />);
    expect(screen.getByRole("link", { name: "Jobs" })).toHaveAttribute("href", "/jobs");
    expect(screen.queryByRole("link", { name: /Technical Program Manager/ })).toBeNull();
    expect(screen.getByText("Scale AI · Technical Program Manager")).toHaveAttribute("aria-current", "page");
    expect(document.title).toBe("Jobs › Scale AI · Technical Program Manager");
  });
});
