import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api/queries", () => ({
  useDiscoveryRuns: () => ({
    isLoading: false,
    error: null,
    data: [
      { id: "1", source: "greenhouse", board: "exampleco", started_at: new Date().toISOString(), finished_at: new Date().toISOString(), found: 12, new: 3, error: null },
      { id: "2", source: "remoteok", board: null, started_at: new Date().toISOString(), finished_at: new Date().toISOString(), found: 0, new: 0, error: "HTTP 503" },
    ],
  }),
}));

import { RunsDrawer } from "./RunsDrawer";

describe("RunsDrawer", () => {
  it("lists each source with counts and errors", () => {
    render(<RunsDrawer open onOpenChange={() => undefined} />);
    expect(screen.getByText(/greenhouse/i)).toBeInTheDocument();
    expect(screen.getByText(/exampleco/)).toBeInTheDocument();
    expect(screen.getByText(/3 new/)).toBeInTheDocument();
    expect(screen.getByText("HTTP 503")).toBeInTheDocument();
  });
});
