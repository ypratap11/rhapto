import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { UsageSection } from "./UsageSection";
import type { UsageOut } from "@/lib/api/queries";

const zeroSummary = {
  calls: 0,
  input_tokens: 0,
  output_tokens: 0,
  cache_read_tokens: 0,
  cache_creation_tokens: 0,
  cost_usd: null,
  unpriced_calls: 0,
};

const usage: UsageOut = {
  totals: {
    ...zeroSummary,
    calls: 12,
    input_tokens: 24000,
    output_tokens: 8000,
    cost_usd: 3.456,
  },
  last_30_days: {
    ...zeroSummary,
    calls: 5,
    input_tokens: 10000,
    output_tokens: 3000,
    cost_usd: 1.2,
  },
  recent: [
    {
      package_id: "pkg-1",
      job_id: "job-1",
      company: "ExampleCo",
      job_title: "Program Manager",
      model: "claude-sonnet-5",
      calls: 2,
      input_tokens: 1000,
      output_tokens: 400,
      cost_usd: 0.006,
      created_at: "2026-09-15T00:00:00Z",
    },
  ],
};

let data: UsageOut | undefined = usage;
let isLoading = false;
let error: unknown = null;

vi.mock("@/lib/api/queries", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/queries")>()),
  useUsageSummary: () => ({ data, isLoading, error }),
}));

describe("UsageSection", () => {
  beforeEach(() => {
    data = usage;
    isLoading = false;
    error = null;
  });

  it("renders all-time and last-30-day call/token counts", () => {
    render(<UsageSection />);
    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getByText("24,000")).toBeInTheDocument();
    expect(screen.getByText("8,000")).toBeInTheDocument();
    expect(screen.getByText("5")).toBeInTheDocument();
    expect(screen.getByText("10,000")).toBeInTheDocument();
  });

  it("shows the estimated cost when it is non-null", () => {
    render(<UsageSection />);
    expect(screen.getByText("$3.46")).toBeInTheDocument();
    expect(screen.getByText("$1.20")).toBeInTheDocument();
  });

  it("hides the cost figure and shows a fallback when cost_usd is null", () => {
    data = {
      totals: { ...zeroSummary, calls: 3, input_tokens: 100, unpriced_calls: 3 },
      last_30_days: { ...zeroSummary },
      recent: [],
    };
    render(<UsageSection />);
    expect(screen.queryByText(/^\$/)).not.toBeInTheDocument();
    expect(screen.getAllByText(/not available|—/i).length).toBeGreaterThan(0);
  });

  it("lists recent runs with a link to the package review page", () => {
    render(<UsageSection />);
    const link = screen.getByRole("link", { name: /ExampleCo/i });
    expect(link).toHaveAttribute("href", "/jobs/job-1/packages/pkg-1");
    expect(screen.getByText("Program Manager")).toBeInTheDocument();
  });

  it("renders a loading state while the summary is in flight", () => {
    isLoading = true;
    data = undefined;
    render(<UsageSection />);
    expect(screen.getByTestId("usage-section-skeleton")).toBeInTheDocument();
  });

  it("renders an error state when the summary fails to load", () => {
    isLoading = false;
    error = new Error("boom");
    data = undefined;
    render(<UsageSection />);
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });
});
