import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { PackageListItem } from "@/lib/api/queries";
import { ResumeTable } from "./ResumeTable";

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
  violations: 0,
};

describe("ResumeTable rows", () => {
  it("shows the company, the role, a plain status word and the fit", () => {
    render(<ResumeTable rows={[row]} />);
    const link = screen.getByRole("link");
    expect(within(link).getByText("ExampleCo")).toBeInTheDocument();
    expect(within(link).getByText("Technical Program Manager")).toBeInTheDocument();
    expect(within(link).getByText("Draft")).toBeInTheDocument();
    expect(within(link).getByRole("img", { name: "Fit 82" })).toBeInTheDocument();
  });

  it.each([
    ["ready", "Ready to send", "Review"],
    ["draft", "Draft", "Review"],
    ["blocked", "Needs attention", "Fix"],
  ])("a %s row says %s and ends in the text %s, inside its one link", (status, word, action) => {
    render(<ResumeTable rows={[{ ...row, status }]} />);
    const link = screen.getByRole("link");
    expect(within(link).getByText(word)).toBeInTheDocument();
    expect(within(link).getByText(action, { exact: true })).toBeInTheDocument();
  });

  it("is exactly one link per row, to that resume, named by company, role and status", () => {
    render(<ResumeTable rows={[row, { ...row, id: "p2", job_id: "j2", company: "Globex", status: "blocked" }]} />);
    const links = screen.getAllByRole("link");
    expect(links).toHaveLength(2);
    expect(links[0]).toHaveAttribute("href", "/jobs/j1/packages/p1");
    expect(links[1]).toHaveAttribute("href", "/jobs/j2/packages/p2");
    expect(links[0]).toHaveAccessibleName("ExampleCo, Technical Program Manager, Draft");
    expect(links[1]).toHaveAccessibleName("Globex, Technical Program Manager, Needs attention");
    expect(links[0].className).toContain("min-h-11");
  });

  it("has no buttons and no row actions, and none of the old columns", () => {
    const { container } = render(<ResumeTable rows={[{ ...row, status: "blocked", violations: 2 }]} />);
    expect(screen.queryAllByRole("button")).toHaveLength(0);
    for (const gone of [/mark ready/i, /regenerate/i, /skip/i, /\bmode\b/i, /\btune\b/i, /\bv2\b/, /guardrail/i, /violation/i, /data pm/i]) {
      expect(container.textContent).not.toMatch(gone);
    }
  });

  it("falls back to readable words for a missing company or title", () => {
    render(<ResumeTable rows={[{ ...row, company: null, title: null }]} />);
    expect(screen.getByRole("link")).toHaveAccessibleName("Unknown company, Untitled role, Draft");
  });

  it("shows an unknown status as it came rather than hiding the row", () => {
    render(<ResumeTable rows={[{ ...row, status: "archived" }]} />);
    expect(screen.getByText("archived")).toBeInTheDocument();
  });
});
