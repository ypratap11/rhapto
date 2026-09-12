import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { PackageListItem } from "@/lib/api/queries";
import type { TrackInfo } from "@/components/queue/JobCard";
import { PackageTable } from "./PackageTable";

const rows: PackageListItem[] = [
  {
    id: "pkg-1",
    job_id: "job-1",
    company: "Exampleco",
    title: "Staff Engineer",
    status: "draft",
    version: 1,
    best_fit: 82,
    best_track_id: "track-1",
    application_status: null,
    created_at: new Date().toISOString(),
  },
  {
    id: "pkg-2",
    job_id: "job-2",
    company: "Blockedco",
    title: "Senior Engineer",
    status: "blocked",
    version: 2,
    best_fit: 40,
    best_track_id: null,
    application_status: null,
    created_at: new Date().toISOString(),
  },
];

const tracks: Record<string, TrackInfo> = { "track-1": { name: "Backend", min_fit: 70 } };

describe("PackageTable", () => {
  it("renders a row per package with status badges and a Review link to the right route", () => {
    render(<PackageTable rows={rows} tracks={tracks} filter="review" />);

    expect(screen.getByText("Exampleco")).toBeInTheDocument();
    expect(screen.getByText("Blockedco")).toBeInTheDocument();
    expect(screen.getByText("v1 · draft")).toBeInTheDocument();
    expect(screen.getByText("v2 · blocked")).toBeInTheDocument();

    const reviewLinks = screen.getAllByRole("link", { name: /review/i });
    expect(reviewLinks).toHaveLength(2);
    expect(reviewLinks[0]).toHaveAttribute("href", "/jobs/job-1/packages/pkg-1");
    expect(reviewLinks[1]).toHaveAttribute("href", "/jobs/job-2/packages/pkg-2");
  });

  it("shows the review empty state when there is nothing to review", () => {
    render(<PackageTable rows={[]} tracks={{}} filter="review" />);
    expect(screen.getByText("Nothing to review")).toBeInTheDocument();
  });
});
