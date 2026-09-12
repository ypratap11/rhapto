import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { NextUp } from "./NextUp";
import type { JobOut } from "@/lib/api/queries";

vi.mock("./JobActionButton", () => ({ JobActionButton: ({ job }: { job: JobOut }) => <div>action:{job.id}</div> }));

const skipJob = vi.fn();
const unskipAll = vi.fn();
let skippedData: string[] = [];
vi.mock("@/lib/skipped", () => ({
  useSkipped: () => skippedData,
  skipJob: (id: string) => skipJob(id),
  unskipAll: () => unskipAll(),
}));

vi.mock("@/lib/api/queries", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/queries")>()),
  useTracks: () => ({ data: [{ id: "t1", name: "Data PM", min_fit: 60 }] }),
}));

const base = (over: Partial<JobOut>): JobOut => ({
  id: "j",
  source: "manual",
  company: "ExampleCo",
  title: "Data PM role",
  location: null,
  url: null,
  jd_text: "x",
  extracted: null,
  discovered_at: "2026-09-01T00:00:00Z",
  latest_package: null,
  application_status: null,
  best_track_id: "t1",
  best_fit: 70,
  rescued: false,
  scores: [],
  ...over,
});

const jobs = [
  base({ id: "a", best_fit: 60, title: "Job A" }),
  base({ id: "b", best_fit: 90, title: "Job B" }),
  base({ id: "c", best_fit: 85, title: "Job C" }),
  base({ id: "d", best_fit: 75, title: "Job D" }),
  base({ id: "e", best_fit: 65, title: "Job E" }),
  base({ id: "f", best_fit: 55, title: "Job F" }),
];

describe("NextUp", () => {
  beforeEach(() => {
    skippedData = [];
    skipJob.mockClear();
    unskipAll.mockClear();
  });

  it("ranks the top five jobs by fit, one to five", () => {
    render(<NextUp jobs={jobs} />);
    const list = screen.getAllByRole("listitem");
    expect(list).toHaveLength(5);
    expect(screen.getByText("action:b")).toBeInTheDocument();
    expect(screen.getByText("action:c")).toBeInTheDocument();
    expect(screen.getByText("action:d")).toBeInTheDocument();
    expect(screen.getByText("action:e")).toBeInTheDocument();
    expect(screen.getByText("action:a")).toBeInTheDocument();
    expect(screen.queryByText("action:f")).not.toBeInTheDocument();
    expect(screen.getAllByText(/^[1-5]$/)).toHaveLength(5);
  });

  it("hides a skipped job", () => {
    skippedData = ["b"];
    render(<NextUp jobs={jobs} />);
    expect(screen.queryByText("action:b")).not.toBeInTheDocument();
    expect(screen.getByText("action:f")).toBeInTheDocument();
  });

  it("calls skipJob with the row's job id when Skip is clicked", async () => {
    render(<NextUp jobs={jobs} />);
    const user = userEvent.setup({ delay: null });
    await user.click(screen.getByRole("button", { name: /skip job b/i }));
    expect(skipJob).toHaveBeenCalledWith("b");
  });

  it("chips the mode of the package waiting for review, and nothing when there is none", () => {
    render(
      <NextUp
        jobs={[
          base({ id: "tuned", best_fit: 95, title: "Tuned job", latest_package: { id: "p1", version: 1, status: "draft", mode: "tune", created_at: "2026-09-10T00:00:00Z" } }),
          base({ id: "built", best_fit: 94, title: "Built job", latest_package: { id: "p2", version: 1, status: "draft", mode: "blocks", created_at: "2026-09-10T00:00:00Z" } }),
          base({ id: "untailored", best_fit: 93, title: "Untailored job" }),
        ]}
      />,
    );
    expect(screen.getByText("tune")).toBeInTheDocument();
    expect(screen.getByText("blocks")).toBeInTheDocument();
    // One chip per package, so the job with no package contributes none.
    expect(screen.getAllByText(/^(tune|blocks)$/)).toHaveLength(2);
  });

  it("renders an empty state when there are no jobs", () => {
    render(<NextUp jobs={[]} />);
    expect(screen.getByText(/nothing to do/i)).toBeInTheDocument();
  });

  it("shows a Show skipped link that clears the skip list when jobs are skipped", async () => {
    skippedData = ["b"];
    render(<NextUp jobs={jobs} />);
    const user = userEvent.setup({ delay: null });
    await user.click(screen.getByRole("button", { name: /show skipped/i }));
    expect(unskipAll).toHaveBeenCalled();
  });
});
