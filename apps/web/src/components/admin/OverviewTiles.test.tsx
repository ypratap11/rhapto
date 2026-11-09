import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { OverviewTiles } from "./OverviewTiles";
import type { OverviewOut } from "@/lib/admin/types";

const base: OverviewOut = {
  signups_total: 31, signups_today: 6, free_spend_month_usd: "18.40", budget_usd: 50,
  accounts: 31, account_cap: 50, want_more_users: 7, failed_7d: 4, alerts: [],
};

describe("OverviewTiles", () => {
  it("renders the five values", () => {
    render(<OverviewTiles overview={base} />);
    expect(screen.getByTestId("value-signups").textContent).toBe("31");
    expect(screen.getByTestId("value-spend").textContent).toBe("$18.40");
    expect(screen.getByTestId("value-limit").textContent).toBe("31 / 50");
    expect(screen.getByTestId("value-more").textContent).toBe("7");
    expect(screen.getByTestId("value-failed").textContent).toBe("4");
    expect(screen.getByText(/failed runs.*7 days/i)).toBeTruthy();
    expect(screen.getByText(/\+6 today/)).toBeTruthy();
  });
  it("labels the sign-in tile an estimate", () => {
    render(<OverviewTiles overview={base} />);
    expect(screen.getByText(/estimate/i)).toBeTruthy();
  });
  it("shows no budget set and no spend bar when the budget is null", () => {
    render(<OverviewTiles overview={{ ...base, budget_usd: null }} />);
    expect(screen.getByText("no budget set")).toBeTruthy();
    expect(screen.queryByTestId("spend-bar")).toBeNull();
  });
  it("bar width is spend over budget", () => {
    render(<OverviewTiles overview={base} />);
    expect(screen.getByTestId("spend-bar").style.width).toBe("36.8%");
  });
  it("clamps the bar at 100%", () => {
    render(<OverviewTiles overview={{ ...base, free_spend_month_usd: "80.00" }} />);
    expect(screen.getByTestId("spend-bar").style.width).toBe("100%");
  });
});
