import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ApplicationCard } from "./ApplicationCard";
import type { ApplicationOut } from "@/lib/api/queries";

vi.mock("@dnd-kit/core", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@dnd-kit/core")>()),
  useDraggable: () => ({ attributes: {}, listeners: {}, setNodeRef: () => undefined, transform: null, isDragging: false }),
}));

const application = {
  id: "a1",
  job: { id: "j1", company: "ExampleCo", title: "Data Platform PM" },
  package_id: "p1",
  status: "applied",
  applied_at: "2026-09-08T10:00:00Z",
  notes: "",
  status_history: [],
  created_at: "2026-09-07T10:00:00Z",
  updated_at: "2026-09-08T10:00:00Z",
} as ApplicationOut;

describe("ApplicationCard", () => {
  it("renders company, title, applied date, and a package link", () => {
    render(<ApplicationCard application={application} onOpen={vi.fn()} />);
    expect(screen.getByText("ExampleCo")).toBeInTheDocument();
    expect(screen.getByText("Data Platform PM")).toBeInTheDocument();
    expect(screen.getByText(/applied 8 Sep 2026/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /package/i })).toHaveAttribute("href", "/jobs/j1/packages/p1");
    expect(screen.getByRole("button", { name: /open/i })).toBeInTheDocument();
  });
});
