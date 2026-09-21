import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ProfileSummaryCard } from "./ProfileSummaryCard";

function panel(): HTMLElement {
  const el = screen.getByRole("dialog");
  return el;
}

describe("ProfileSummaryCard", () => {
  it("renders the title, summary and an Edit button", () => {
    render(
      <ProfileSummaryCard id="watchlist" title="Watchlist" summary="7 companies watched" open={false} onOpenChange={vi.fn()}>
        <p>editor</p>
      </ProfileSummaryCard>,
    );
    expect(screen.getByRole("heading", { name: "Watchlist" })).toBeInTheDocument();
    expect(screen.getByText("7 companies watched")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Edit Watchlist" })).toBeInTheDocument();
  });

  // SheetContent ships `data-[side=right]:sm:max-w-sm` (384px). A max-width beats a width, so the
  // `w-[520px]` this card asked for never applied and every profile editor rendered at 384px --
  // which is what squeezed the watchlist's table into a horizontal scrollbar. The override must
  // carry the same `data-[side=right]:` variant: that compiles to an attribute selector, so a
  // plain `sm:max-w-*` loses on specificity and the primitive silently wins again.
  it("overrides the sheet's max-width so the requested width actually applies", () => {
    render(
      <ProfileSummaryCard id="tracks" title="Tracks" summary="3 tracks" open onOpenChange={vi.fn()}>
        <p>editor</p>
      </ProfileSummaryCard>,
    );
    expect(panel().className).toMatch(/data-\[side=right\]:sm:max-w-\[/);
    expect(panel().className).toContain("520px");
  });

  it("gives a wide editor more room than the default one", () => {
    render(
      <ProfileSummaryCard id="watchlist" title="Watchlist" summary="7 watched" open onOpenChange={vi.fn()} wide>
        <p>editor</p>
      </ProfileSummaryCard>,
    );
    expect(panel().className).toContain("920px");
    expect(panel().className).toMatch(/data-\[side=right\]:sm:max-w-\[/);
  });

  it("caps the panel at the viewport so it cannot overflow a narrow screen", () => {
    render(
      <ProfileSummaryCard id="watchlist" title="Watchlist" summary="7 watched" open onOpenChange={vi.fn()} wide>
        <p>editor</p>
      </ProfileSummaryCard>,
    );
    expect(panel().className).toContain("96vw");
  });
});
