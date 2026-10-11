import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { StatTile } from "./stat-tile";

describe("StatTile", () => {
  it("is a link when given an href, at least 44px tall", () => {
    render(<StatTile tone="peach" value={2} label="To review" hint="Tailored, not sent yet" href="/resumes?tab=review" />);
    const link = screen.getByRole("link", { name: /To review/ });
    expect(link).toHaveAttribute("href", "/resumes?tab=review");
    expect(link).toHaveTextContent("2");
    expect(link).toHaveTextContent("Tailored, not sent yet");
    expect(link.className).toContain("min-h-11");
  });

  it("is a toggle button otherwise", async () => {
    const onClick = vi.fn();
    const user = userEvent.setup({ delay: null });
    render(<StatTile tone="blue" value={1} label="Interviewing" onClick={onClick} pressed />);
    const button = screen.getByRole("button", { name: /Interviewing/ });
    expect(button).toHaveAttribute("aria-pressed", "true");
    expect(button.className).toContain("border-foreground");
    await user.click(button);
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("lifts on hover only when motion is allowed, and shows a focus ring", () => {
    render(<StatTile tone="mint" value={0} label="Applied" onClick={() => {}} />);
    const cls = screen.getByRole("button").className;
    expect(cls).toContain("motion-safe:hover:-translate-y-0.5");
    expect(cls).toContain("focus-visible:ring-3");
  });

  it("quiets the number when muted", () => {
    render(<StatTile tone="amber" value={0} label="Offers" onClick={() => {}} muted />);
    expect(screen.getByText("0").className).toContain("text-muted-foreground");
    expect(screen.getByText("0").className).not.toContain("text-fit-mid");
  });
});
