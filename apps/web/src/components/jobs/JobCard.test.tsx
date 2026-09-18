import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { JobOut } from "@/lib/api/queries";
import { JobCard } from "./JobCard";

vi.mock("./NotInterestedButton", () => ({ NotInterestedButton: () => <button>Not interested</button> }));
vi.mock("@/components/queue/TailorButton", () => ({ TailorButton: () => <button>Tailor</button> }));

const job = {
  id: "j1",
  source: "themuse",
  company: "ExampleCo",
  title: "Technical Program Manager",
  location: "Austin, TX",
  url: "https://example.com/job",
  jd_text: "Lead the data platform migration across product and analytics teams.",
  extracted: null,
  discovered_at: "2026-09-13T10:00:00Z",
  posted_at: "2026-09-12T10:00:00Z",
  latest_package: null,
  application_status: null,
  best_fit: 82,
  best_track_id: "t1",
  bucket: "fit",
  location_tier: "preferred",
  rescued: false,
  repost_of: null,
  scores: [],
  hidden_at: null,
  unlisted_at: null,
  salary_text: "$150k – $180k",
  search_name: "Program management",
} as unknown as JobOut;

const track = { name: "Data PM", min_fit: 60 };

describe("JobCard", () => {
  // Must run before any other test in this file renders a JobCard: Base UI's dev warnings are
  // logged at most once per unique message for the life of the module (see
  // `@base-ui/utils/createLogOnce`), so once some other test's render has already triggered it,
  // a later spy here would see nothing regardless of whether the bug is still present. Base UI
  // warns when a Button renders a non-<button> element (the Tailor link) while its `nativeButton`
  // prop is still true — a real accessibility defect (the element claims native button semantics
  // it can't back), not just console noise. Nothing else asserts on console output, so this would
  // otherwise ship silently every time.
  it("does not warn on the console about the Tailor button's element type", () => {
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
    render(<JobCard job={job} track={track} />);
    expect(errorSpy).not.toHaveBeenCalled();
    expect(warnSpy).not.toHaveBeenCalled();
    errorSpy.mockRestore();
    warnSpy.mockRestore();
  });

  it("shows the fit ring, the logo initial, chips, salary and the posted line", () => {
    render(<JobCard job={job} track={track} />);
    expect(screen.getByRole("img", { name: "Fit 82" })).toBeInTheDocument();
    expect(screen.getByTestId("logo-placeholder")).toHaveTextContent("E");
    expect(screen.getByRole("link", { name: /Technical Program Manager/ })).toHaveAttribute("href", "/jobs/j1");
    for (const chip of ["Data PM", "The Muse", "Preferred area"]) expect(screen.getByText(chip)).toBeInTheDocument();
    expect(screen.getByText("$150k – $180k")).toBeInTheDocument();
    expect(screen.getByText(/Posted ·/)).toBeInTheDocument();
  });

  it("marks a repost and a no-longer-listed job", () => {
    render(<JobCard job={{ ...job, repost_of: "j0", unlisted_at: "2026-09-14T00:00:00Z" } as JobOut} track={track} />);
    expect(screen.getByText("Reposted")).toBeInTheDocument();
    expect(screen.getByText("No longer listed")).toBeInTheDocument();
  });

  it("shows a dashed ring while the worker is still scoring", () => {
    render(<JobCard job={{ ...job, best_fit: null } as JobOut} track={track} />);
    expect(screen.getByRole("img", { name: /not scored yet/i })).toBeInTheDocument();
  });
});
