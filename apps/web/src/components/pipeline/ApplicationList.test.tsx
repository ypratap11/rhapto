import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { ApplicationOut } from "@/lib/api/queries";
import { ApplicationList } from "./ApplicationList";

function app(over: Partial<ApplicationOut> & { id: string; job: ApplicationOut["job"]; status: string }): ApplicationOut {
  return {
    applied_at: null,
    closed_reason: null,
    created_at: "2026-09-01T00:00:00Z",
    follow_up_at: null,
    notes: "",
    package_id: null,
    status_history: [],
    updated_at: "2026-09-01T00:00:00Z",
    ...over,
  } as ApplicationOut;
}

const applications: ApplicationOut[] = [
  app({
    id: "a1",
    job: { id: "j1", company: "Zeta Corp", title: "PM" },
    status: "applied",
    applied_at: "2026-09-08",
    updated_at: "2026-09-09T10:00:00Z",
  }),
  app({
    id: "a2",
    job: { id: "j2", company: "Acme Inc", title: "Engineer" },
    status: "applied",
    applied_at: "2026-09-05",
    updated_at: "2026-09-07T10:00:00Z",
    follow_up_at: "2026-09-21",
  }),
  app({
    id: "a3",
    job: { id: "j3", company: "Acme Inc", title: "Director" },
    status: "interview",
    applied_at: "2026-09-01",
    updated_at: "2026-09-10T10:00:00Z",
  }),
  app({
    id: "a4",
    job: { id: "j4", company: "Globex", title: "Analyst" },
    status: "closed",
    applied_at: "2026-08-01",
    updated_at: "2026-08-02T10:00:00Z",
  }),
];

describe("ApplicationList", () => {
  it("shows the five pipeline tabs", () => {
    render(<ApplicationList applications={applications} selectedId={null} onSelect={vi.fn()} />);
    for (const label of ["Applied", "Screen", "Interview", "Offer", "Closed"]) {
      expect(screen.getByRole("tab", { name: label })).toBeInTheDocument();
    }
  });

  it("defaults to the Applied tab and hides other statuses", () => {
    render(<ApplicationList applications={applications} selectedId={null} onSelect={vi.fn()} />);
    expect(screen.getByText("Zeta Corp")).toBeInTheDocument();
    expect(screen.getByText("Acme Inc")).toBeInTheDocument();
    expect(screen.queryByText("Director")).not.toBeInTheDocument();
    expect(screen.queryByText("Analyst")).not.toBeInTheDocument();
  });

  it("switches tabs to show that status's applications only", async () => {
    const user = userEvent.setup({ delay: null });
    render(<ApplicationList applications={applications} selectedId={null} onSelect={vi.fn()} />);
    await user.click(screen.getByRole("tab", { name: "Interview" }));
    expect(screen.getByText("Director")).toBeInTheDocument();
    expect(screen.queryByText("Zeta Corp")).not.toBeInTheDocument();
  });

  it("filters by company or role within the active tab", async () => {
    const user = userEvent.setup({ delay: null });
    render(<ApplicationList applications={applications} selectedId={null} onSelect={vi.fn()} />);
    await user.type(screen.getByLabelText("Search applications"), "acme");
    expect(screen.getByText("Acme Inc")).toBeInTheDocument();
    expect(screen.queryByText("Zeta Corp")).not.toBeInTheDocument();
  });

  it("shows the status pill, applied date, and a follow-up chip", () => {
    render(<ApplicationList applications={applications} selectedId={null} onSelect={vi.fn()} />);
    const card = screen.getByText("Acme Inc").closest("button");
    if (!card) throw new Error("card not found");
    expect(within(card).getByText("Applied")).toBeInTheDocument();
    expect(within(card).getByText("Applied · 5 Sep 2026")).toBeInTheDocument();
    expect(within(card).getByText("Follow up 21 Sep 2026")).toBeInTheDocument();
    const otherCard = screen.getByText("Zeta Corp").closest("button");
    if (!otherCard) throw new Error("card not found");
    expect(within(otherCard).queryByText(/Follow up/)).not.toBeInTheDocument();
  });

  it("re-sorts by company when Company is chosen", async () => {
    const user = userEvent.setup({ delay: null });
    render(<ApplicationList applications={applications} selectedId={null} onSelect={vi.fn()} />);
    const companiesBefore = screen.getAllByRole("button").map((b) => b.querySelector("p")?.textContent);
    expect(companiesBefore).toEqual(["Zeta Corp", "Acme Inc"]);

    await user.click(screen.getByLabelText("Sort by"));
    await user.click(await screen.findByRole("option", { name: "Company" }));

    const companiesAfter = screen.getAllByRole("button").map((b) => b.querySelector("p")?.textContent);
    expect(companiesAfter).toEqual(["Acme Inc", "Zeta Corp"]);
  });

  it("fires onSelect with the clicked card's id and marks it current", () => {
    const onSelect = vi.fn();
    render(<ApplicationList applications={applications} selectedId="a2" onSelect={onSelect} />);
    const selectedCard = screen.getByText("Acme Inc").closest("button");
    const otherCard = screen.getByText("Zeta Corp").closest("button");
    expect(selectedCard).toHaveAttribute("aria-current", "true");
    expect(otherCard).toHaveAttribute("aria-current", "false");
    otherCard?.click();
    expect(onSelect).toHaveBeenCalledWith("a1");
  });
});
