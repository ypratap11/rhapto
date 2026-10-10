import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { WaitingBanner } from "./WaitingBanner";

describe("WaitingBanner", () => {
  it("renders nothing when nothing is waiting", () => {
    const { container } = render(<WaitingBanner count={0} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("says one resume is waiting and links to the review tab", () => {
    render(<WaitingBanner count={1} />);
    expect(screen.getByText("1 resume is waiting for your review.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Review it →" })).toHaveAttribute("href", "/resumes?tab=review");
  });

  it("says how many are waiting", () => {
    render(<WaitingBanner count={3} />);
    expect(screen.getByText("3 resumes are waiting for your review.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Review them →" })).toBeInTheDocument();
  });
});
