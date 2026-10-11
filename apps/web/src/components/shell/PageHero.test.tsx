import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PageHero } from "./PageHero";

describe("PageHero", () => {
  it("has the page's one h1, the summary, the aside and the children", () => {
    render(
      <PageHero title="Good morning, Maya" subtitle={<p>3 strong matches are waiting.</p>} aside={<p>card</p>}>
        <p>tiles</p>
      </PageHero>,
    );
    expect(screen.getByRole("heading", { level: 1, name: "Good morning, Maya" })).toBeInTheDocument();
    expect(screen.getByText("3 strong matches are waiting.")).toBeInTheDocument();
    expect(screen.getByText("card")).toBeInTheDocument();
    expect(screen.getByText("tiles")).toBeInTheDocument();
  });

  it("keeps content in the page column and only the wash breaks out", () => {
    render(<PageHero title="x" />);
    const hero = screen.getByTestId("page-hero");
    expect(hero.className).toContain("before:bg-page-hero");
    expect(hero.className).toContain("before:w-screen");
    expect(hero.className).not.toMatch(/(^|\s)w-screen/);
    expect(hero.className).not.toMatch(/max-w-/);
  });

  it("leaves out an empty summary, aside and children", () => {
    const { container } = render(<PageHero title="x" />);
    expect(container.querySelector("p")).toBeNull();
  });
});
