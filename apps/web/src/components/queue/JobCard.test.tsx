import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { JobCard } from "./JobCard";
import type { JobOut } from "@/lib/api/queries";

vi.mock("./TailorButton", () => ({ TailorButton: () => <button>Tailor</button> }));

const job: JobOut = {
  id: "j1",
  source: "manual",
  company: "ExampleCo",
  title: "Data Platform Program Manager",
  location: null,
  url: "https://example.com/job",
  jd_text: "lorem",
  extracted: null,
  discovered_at: "2026-09-09T10:00:00Z",
  latest_package: { id: "p1", version: 2, status: "blocked", created_at: "2026-09-09T11:00:00Z" },
  application_status: "applied",
};

describe("JobCard", () => {
  it("shows company, title, package and application badges, and links to the latest package", () => {
    render(<JobCard job={job} onDelete={vi.fn()} />);
    expect(screen.getByText("ExampleCo")).toBeInTheDocument();
    expect(screen.getByText("Data Platform Program Manager")).toBeInTheDocument();
    expect(screen.getByText(/v2 · blocked/i)).toBeInTheDocument();
    expect(screen.getByText("Applied")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /review/i })).toHaveAttribute("href", "/jobs/j1/packages/p1");
    expect(screen.getByRole("link", { name: /posting/i })).toHaveAttribute("href", "https://example.com/job");
  });
});
