import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { ApplicationOut, DashboardOut, PackageListItem } from "@/lib/api/queries";
import { ActiveApplications } from "./ActiveApplications";

const useApplicationsMock = vi.fn();
const usePackageListMock = vi.fn();
const useDashboardMock = vi.fn();
vi.mock("@/lib/api/queries", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/queries")>()),
  useApplications: () => useApplicationsMock(),
  usePackageList: (filter: string) => usePackageListMock(filter),
  useDashboard: () => useDashboardMock(),
}));

function application(over: Partial<ApplicationOut> & { id: string; job: ApplicationOut["job"] }): ApplicationOut {
  return {
    applied_at: null,
    closed_reason: null,
    created_at: "2026-09-01T00:00:00Z",
    follow_up_at: null,
    notes: "",
    package_id: null,
    status: "applied",
    status_history: [],
    updated_at: "2026-09-01T00:00:00Z",
    ...over,
  } as ApplicationOut;
}

const emptyChecklist = {} as DashboardOut["checklist"];
// Computed at run time (not hardcoded) so the fixture stays "due today" whenever this suite runs.
const todayIso = new Date().toISOString().slice(0, 10);

function dashboardData(dueFollowups: DashboardOut["due_followups"]): DashboardOut {
  return { checklist: emptyChecklist, due_followups: dueFollowups, needs_review_count: 0, new_fit_count: 0, saved_searches: [] };
}

describe("ActiveApplications", () => {
  it("gives a due-today follow-up its own card when it is not one of the recent three", () => {
    useApplicationsMock.mockReturnValue({
      data: {
        columns: {
          applied: [
            application({ id: "a1", updated_at: "2026-09-17T00:00:00Z", job: { id: "j1", company: "Acme", title: "PM" } }),
            application({ id: "a2", updated_at: "2026-09-16T00:00:00Z", job: { id: "j2", company: "Beta", title: "Eng" } }),
            application({ id: "a3", updated_at: "2026-09-15T00:00:00Z", job: { id: "j3", company: "Gamma", title: "Designer" } }),
          ],
          // Older than all three above, so it is not among the recent three — but its follow-up
          // is due today, and it must still show up.
          discovered: [application({ id: "a4", updated_at: "2020-01-01T00:00:00Z", job: { id: "j4", company: "Delta", title: "Analyst" } })],
        },
      },
      isLoading: false,
      error: null,
    });
    usePackageListMock.mockReturnValue({ data: [], isLoading: false, error: null });
    useDashboardMock.mockReturnValue({
      data: dashboardData([{ application_id: "a4", follow_up_at: `${todayIso}T00:00:00Z`, job: { id: "j4", company: "Delta", title: "Analyst" }, status: "screen" }]),
      isLoading: false,
      error: null,
    });

    render(<ActiveApplications />);

    expect(screen.getByText("Delta")).toBeInTheDocument();
    const card = screen.getByText("Delta").closest("a");
    expect(card).not.toBeNull();
    expect(card).toHaveTextContent("Follow up today");
  });

  it("flags a due-today follow-up on its existing recent-three card exactly once, without duplicating it", () => {
    useApplicationsMock.mockReturnValue({
      data: {
        columns: {
          applied: [
            application({ id: "a1", updated_at: "2026-09-17T00:00:00Z", job: { id: "j1", company: "Acme", title: "PM" } }),
            application({ id: "a2", updated_at: "2026-09-16T00:00:00Z", job: { id: "j2", company: "Beta", title: "Eng" } }),
            application({ id: "a3", updated_at: "2026-09-15T00:00:00Z", job: { id: "j3", company: "Gamma", title: "Designer" } }),
          ],
        },
      },
      isLoading: false,
      error: null,
    });
    usePackageListMock.mockReturnValue({ data: [], isLoading: false, error: null });
    useDashboardMock.mockReturnValue({
      data: dashboardData([{ application_id: "a1", follow_up_at: `${todayIso}T00:00:00Z`, job: { id: "j1", company: "Acme", title: "PM" }, status: "applied" }]),
      isLoading: false,
      error: null,
    });

    render(<ActiveApplications />);

    expect(screen.getAllByText("Acme")).toHaveLength(1);
    expect(screen.getAllByText("Follow up today")).toHaveLength(1);
  });

  it("shows ready-not-applied packages alongside the recent applications", () => {
    useApplicationsMock.mockReturnValue({ data: { columns: {} }, isLoading: false, error: null });
    usePackageListMock.mockReturnValue({
      data: [
        {
          id: "p1",
          job_id: "j5",
          company: "Zeta",
          title: "Recruiter",
          application_status: null,
          best_fit: 80,
          best_track_id: null,
          created_at: "2026-09-01T00:00:00Z",
          mode: "blocks",
          status: "ready",
          version: 1,
        } as PackageListItem,
      ],
      isLoading: false,
      error: null,
    });
    useDashboardMock.mockReturnValue({ data: dashboardData([]), isLoading: false, error: null });

    render(<ActiveApplications />);

    expect(screen.getByText("Zeta")).toBeInTheDocument();
    expect(screen.getByText("Ready to apply")).toBeInTheDocument();
  });

  it("shows an empty state when there is nothing in flight", () => {
    useApplicationsMock.mockReturnValue({ data: { columns: {} }, isLoading: false, error: null });
    usePackageListMock.mockReturnValue({ data: [], isLoading: false, error: null });
    useDashboardMock.mockReturnValue({ data: dashboardData([]), isLoading: false, error: null });

    render(<ActiveApplications />);

    expect(screen.getByText(/nothing in flight yet/i)).toBeInTheDocument();
  });

  it("shows a loading placeholder while applications, ready packages or the dashboard call are in flight", () => {
    useApplicationsMock.mockReturnValue({ data: undefined, isLoading: true, error: null });
    usePackageListMock.mockReturnValue({ data: undefined, isLoading: false, error: null });
    useDashboardMock.mockReturnValue({ data: undefined, isLoading: false, error: null });

    render(<ActiveApplications />);

    expect(screen.queryByText(/nothing in flight yet/i)).not.toBeInTheDocument();
  });
});
