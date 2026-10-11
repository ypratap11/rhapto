import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { JobOut } from "@/lib/api/queries";
import { JdPane } from "./JdPane";

const job = {
  id: "j1",
  title: "Analyst",
  company: "ExampleCo",
  location: null,
  jd_text: "Do the job.",
  extracted: null,
} as unknown as JobOut;

describe("JdPane", () => {
  it("links to the original posting in a new tab without leaking the opener", () => {
    render(<JdPane job={job} postingUrl="https://x.com/j" />);
    const link = screen.getByRole("link", { name: "Open the original posting" });
    expect(link).toHaveAttribute("href", "https://x.com/j");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("renders no link for an unsafe or missing url", () => {
    const { unmount } = render(<JdPane job={job} postingUrl="javascript:alert(1)" />);
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
    unmount();
    render(<JdPane job={job} postingUrl={null} />);
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
    expect(screen.queryByText(/show the full description/i)).not.toBeInTheDocument();
  });
});
