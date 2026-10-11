import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { JobRow } from "./job-row";

describe("JobRow", () => {
  it("shows the fit ring, title, meta and actions", () => {
    render(
      <ul>
        <JobRow fit={82} title="Technical Program Manager" meta={<span>Acme</span>} actions={<button>Tailor</button>} />
      </ul>,
    );
    expect(screen.getByRole("listitem")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Fit 82" })).toBeInTheDocument();
    expect(screen.getByText("Technical Program Manager")).toBeInTheDocument();
    expect(screen.getByText("Acme")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Tailor" })).toBeInTheDocument();
  });

  it("keeps the title on one line from sm up, wrapping on phones, and turns the border on hover", () => {
    render(<JobRow as="div" fit={null} title="Role" />);
    expect(screen.getByText("Role").className).toContain("sm:truncate");
    expect(screen.getByText("Role").className).not.toMatch(/(^|\s)truncate/);
    expect(document.querySelector('[data-slot="job-row"]')!.className).toContain("hover:border-primary");
  });
});
