import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const pathname = { current: "/" };
vi.mock("next/navigation", () => ({ usePathname: () => pathname.current }));

const jobsData: unknown[] = [];
const reviewData: unknown[] = [{ id: "p1" }, { id: "p2" }];

vi.mock("@/lib/api/queries", () => ({
  DEFAULT_REGION: "us",
  useJobs: () => ({ data: jobsData }),
  usePackageList: () => ({ data: reviewData }),
}));

const tailoringCount = { current: 0 };
vi.mock("@/lib/tailoring", () => ({
  useTailoringCount: () => tailoringCount.current,
}));

import { StepBar } from "./StepBar";

describe("StepBar", () => {
  it("marks Find current and shows the review prompt on the root route", () => {
    pathname.current = "/";
    tailoringCount.current = 0;
    render(<StepBar />);
    expect(screen.getByText("Find").closest("li")).toHaveAttribute("aria-current", "step");
    const link = screen.getByRole("link", { name: "2 packages ready to review" });
    expect(link).toHaveAttribute("href", "/packages?filter=review");
  });

  it("marks Apply current on the pipeline route", () => {
    pathname.current = "/pipeline";
    tailoringCount.current = 0;
    render(<StepBar />);
    expect(screen.getByText("Apply").closest("li")).toHaveAttribute("aria-current", "step");
  });

  it("marks Tailor current on the root route only while a tailoring task is running", () => {
    pathname.current = "/";
    tailoringCount.current = 1;
    render(<StepBar />);
    expect(screen.getByText("Tailor").closest("li")).toHaveAttribute("aria-current", "step");
    expect(screen.getByText("Find").closest("li")).not.toHaveAttribute("aria-current", "step");
  });
});
