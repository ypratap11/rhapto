import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
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
    expect(links[0]).toHaveAccessibleName(/^ExampleCo, Technical Program Manager, Draft, made (just now|\d+[mhd] ago), (Light touch|Full rewrite)$/);
    expect(links[1]).toHaveAccessibleName(/^Globex, Technical Program Manager, Needs attention, made (just now|\d+[mhd] ago), (Light touch|Full rewrite)$/);
    expect(links[0]!.className).toContain("min-h-11");
  });

  it("names the mode in the meta line and at the end of the link's name", () => {
    render(<ResumeTable rows={[row, { ...row, id: "p2", mode: "blocks" }]} />);
    const [tune, blocks] = screen.getAllByRole("link");
    expect(within(tune!).getByText("Light touch")).toBeInTheDocument();
    expect(tune).toHaveAccessibleName(/, Light touch$/);
    expect(within(blocks!).getByText("Full rewrite")).toBeInTheDocument();
    expect(blocks).toHaveAccessibleName(/, Full rewrite$/);
  });

  it("has no header row, and the action is a plain element inside the link", () => {
    render(<ResumeTable rows={[row]} />);
    for (const col of ["Company", "Role", "Fit", "Status"]) expect(screen.queryByText(col, { exact: true })).not.toBeInTheDocument();
    const action = within(screen.getByRole("link")).getByText("Review", { exact: true });
    expect(action.tagName).toBe("SPAN");
  });

  it("tells two identical rows apart with when each was made", () => {
    const now = new Date("2026-09-13T12:00:00Z").getTime();
    vi.useFakeTimers({ now });
    try {
      render(<ResumeTable rows={[row, { ...row, id: "p2", created_at: "2026-09-10T12:00:00Z" }]} />);
      const links = screen.getAllByRole("link");
      expect(within(links[0]!).getByText("Made 3h ago")).toBeInTheDocument();
      expect(within(links[1]!).getByText("Made 3d ago")).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
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
    expect(screen.getByRole("link")).toHaveAccessibleName(/^Unknown company, Untitled role, Draft, made /);
  });

  it("shows an unknown status as it came rather than hiding the row", () => {
    render(<ResumeTable rows={[{ ...row, status: "archived" }]} />);
    expect(screen.getByText("archived")).toBeInTheDocument();
  });
});
