import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { PackageListItem } from "@/lib/api/queries";
import { ResumeTable } from "./ResumeTable";

vi.mock("./ResumeRowActions", () => ({ ResumeRowActions: () => <button>Review</button> }));

const row: PackageListItem = {
  id: "p1",
  job_id: "j1",
  company: "ExampleCo",
  title: "Technical Program Manager",
  best_fit: 82,
  best_track_id: "t1",
  status: "draft",
  version: 2,
  mode: "tune",
  application_status: null,
  created_at: "2026-09-13T09:00:00Z",
};

describe("ResumeTable", () => {
  it("shows the fit ring, the version·status pill, the mode chip and when it was created", () => {
    render(<ResumeTable rows={[row]} tracks={{ t1: { name: "Data PM", min_fit: 60 } }} filter="review" />);
    const tr = screen.getByRole("row", { name: /ExampleCo/ });
    expect(within(tr).getByRole("img", { name: "Fit 82" })).toBeInTheDocument();
    expect(within(tr).getByText("v2 · draft")).toBeInTheDocument();
    expect(within(tr).getByText("tune")).toBeInTheDocument();
  });

  it("says what is empty rather than rendering an empty table", () => {
    render(<ResumeTable rows={[]} tracks={{}} filter="ready" />);
    expect(screen.getByText(/nothing ready to apply/i)).toBeInTheDocument();
  });
});
