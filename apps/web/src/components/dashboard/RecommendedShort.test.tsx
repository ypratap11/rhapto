import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/client";
import type { JobOut } from "@/lib/api/queries";
import { RecommendedShort } from "./RecommendedShort";

const push = vi.fn();
const mutateAsync = vi.fn();
const fire = vi.fn();
let recommended: { data: JobOut[]; isLoading: boolean; error: unknown; isPaused: boolean };
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));
vi.mock("@/lib/coach/events", () => ({ fireCoachEvent: (step: string) => fire(step) }));
vi.mock("@/components/jobs/NotInterestedButton", () => ({
  NotInterestedButton: ({ job }: { job: JobOut }) => <button>Not interested in {job.id}</button>,
}));
vi.mock("@/lib/api/queries", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/queries")>()),
  useRecommendedJobs: () => recommended,
  useTracks: () => ({ data: [{ id: "t1", name: "Data PM", min_fit: 70 }] }),
  useTailor: () => ({ mutateAsync }),
}));

const job = (id: string, fit: number) =>
  ({ id, title: `Role ${id}`, company: "ExampleCo", location: "Remote", salary_text: "$150k", best_fit: fit, best_track_id: "t1" }) as unknown as JobOut;

beforeEach(() => {
  push.mockReset();
  fire.mockReset();
  mutateAsync.mockReset().mockResolvedValue({ id: "t1" });
  recommended = { data: Array.from({ length: 7 }, (_, i) => job(`j${i}`, 80)), isLoading: false, error: null, isPaused: false };
});

describe("RecommendedShort", () => {
  it("shows five of seven", () => {
    render(<RecommendedShort />);
    expect(within(screen.getByRole("list")).getAllByRole("listitem")).toHaveLength(5);
  });

  it("says Strong or Good match, never a score, and shows location and salary", () => {
    recommended = { ...recommended, data: [job("a", 90), job("b", 65)] };
    render(<RecommendedShort />);
    expect(screen.getByText("Strong match")).toBeInTheDocument();
    expect(screen.getByText("Good match")).toBeInTheDocument();
    expect(screen.queryByText(/\b(90|65)\b/)).toBeNull();
    expect(screen.getAllByText(/Remote/)).not.toHaveLength(0);
    expect(screen.getAllByText(/\$150k/)).not.toHaveLength(0);
  });

  it("starts one tune task per tap and goes to the coach", async () => {
    const user = userEvent.setup({ delay: null });
    recommended = { ...recommended, data: [job("a", 80)] };
    render(<RecommendedShort />);
    await user.dblClick(screen.getByRole("button", { name: "Tailor" }));
    expect(mutateAsync).toHaveBeenCalledTimes(1);
    expect(mutateAsync).toHaveBeenCalledWith({ jobId: "a", body: { mode: "tune" } });
    expect(push).toHaveBeenCalledWith("/start?task=t1");
    expect(fire).toHaveBeenCalledWith("tailor_started");
  });

  it("explains a refusal and lets the person try again", async () => {
    const user = userEvent.setup({ delay: null });
    recommended = { ...recommended, data: [job("a", 80)] };
    mutateAsync.mockRejectedValueOnce(new ApiError(409, { code: "llm_not_configured", title: "x", detail: "x" } as never, "x"));
    render(<RecommendedShort />);
    await user.click(screen.getByRole("button", { name: "Tailor" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Tailor" })).toBeEnabled();
    expect(push).not.toHaveBeenCalled();
    expect(fire).not.toHaveBeenCalled();
  });

  it("hides a job through the shared Not interested button", () => {
    recommended = { ...recommended, data: [job("a", 80)] };
    render(<RecommendedShort />);
    expect(screen.getByRole("button", { name: "Not interested in a" })).toBeInTheDocument();
  });

  it("says jobs are coming when the list is empty", () => {
    recommended = { ...recommended, data: [] };
    render(<RecommendedShort />);
    expect(screen.getByText("We're finding jobs that fit you. New jobs arrive through the day.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Paste a job instead" })).toHaveAttribute("href", "/start");
  });

  it("shows no empty box and no second banner when the API is down and nothing is cached", () => {
    recommended = { data: [], isLoading: false, error: new Error("down"), isPaused: false };
    render(<RecommendedShort />);
    expect(screen.queryByRole("list")).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.queryByText(/finding jobs that fit you/)).toBeNull();
  });

  it("shows a real ellipsis while starting", async () => {
    mutateAsync.mockReturnValue(new Promise(() => {}));
    const user = userEvent.setup({ delay: null });
    render(<RecommendedShort />);
    await user.click(screen.getAllByRole("button", { name: "Tailor" })[0]!);
    expect(screen.getByRole("button", { name: "Starting…" })).toBeInTheDocument();
  });

  it("links to all matching jobs", () => {
    render(<RecommendedShort />);
    expect(screen.getByRole("link", { name: "See all matching jobs →" })).toHaveAttribute("href", "/jobs");
  });
});
