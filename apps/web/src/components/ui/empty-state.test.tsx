import { render, screen } from "@testing-library/react";
import { Inbox } from "lucide-react";
import { describe, expect, it } from "vitest";
import { EmptyState } from "./empty-state";

describe("EmptyState", () => {
  it("puts the icon in a soft tinted circle and keeps title and description readable", () => {
    const { container } = render(<EmptyState icon={Inbox} title="Nothing yet" description="Come back soon." />);
    const circle = container.querySelector("[data-slot='empty-state-icon']")!;
    expect(circle).toHaveAttribute("aria-hidden", "true");
    expect(circle.className).toContain("rounded-full");
    expect(circle.className).toContain("bg-glow-mid");
    expect(circle.className).toContain("dark:bg-surface-muted");
    expect(screen.getByText("Nothing yet")).toBeInTheDocument();
    expect(screen.getByText("Come back soon.")).toBeInTheDocument();
  });
});
