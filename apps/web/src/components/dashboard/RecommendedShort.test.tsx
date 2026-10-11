import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/client";
import type { JobOut } from "@/lib/api/queries";
import { RecommendedShort } from "./RecommendedShort";

const push = vi.fn();
const mutateAsync = vi.fn();
const fire = vi.fn();
const refetch = vi.fn();
let recommended: { data: JobOut[]; isLoading: boolean; error: unknown; isPaused: boolean; refetch?: () => void };
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));
vi.mock("@/lib/coach/events", () => ({ fireCoachEvent: (step: string) => fire(step) }));
vi.mock("@/components/jobs/NotInterestedButton", () => ({
  NotInterestedButton: ({ job, iconOnly }: { job: JobOut; iconOnly?: boolean }) => (
    <button data-icon-only={iconOnly ? "yes" : "no"}>Not interested in {job.id}</button>
  ),
}));
vi.mock("@/lib/api/queries", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/queries")>()),
  useRecommendedJobs: () => recommended,
  useTracks: () => ({ data: [{ id: "t1", name: "Data PM", min_fit: 70 }] }),
  useTailor: () => ({ mutateAsync }),
}));

const job = (id: string, fit: number) =>
  ({
    id,
    title: `Role ${id}`,
    company: "ExampleCo",
    location: "Remote",
    salary_text: "$150k",
    source: "adzuna",
    best_fit: fit,
    best_track_id: "t1",
    discovered_at: new Date(Date.now() - 3 * 86_400_000).toISOString(),
  }) as unknown as JobOut;

beforeEach(() => {
  push.mockReset();
  fire.mockReset();
  mutateAsync.mockReset().mockResolvedValue({ id: "t1" });
  recommended = { data: Array.from({ length: 7 }, (_, i) => job(`j${i}`, 80)), isLoading: false, error: null, isPaused: false, refetch };
  refetch.mockReset();
});

describe("RecommendedShort", () => {
  it("shows five of seven", () => {
    render(<RecommendedShort />);
    expect(within(screen.getByRole("list")).getAllByRole("listitem")).toHaveLength(5);
  });

  it("shows each job's fit as a ring, with company, location and a salary pill", () => {
    recommended = { ...recommended, data: [job("a", 90), job("b", 65)] };
    render(<RecommendedShort />);
    expect(screen.getByRole("img", { name: "Fit 90" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Fit 65" })).toBeInTheDocument();
    expect(screen.getAllByText("ExampleCo")).toHaveLength(2);
    expect(screen.getAllByText("Remote")).toHaveLength(2);
    expect(screen.getAllByText("$150k")).toHaveLength(2);
  });

  it("marks only jobs found in the last 24 hours as New today", () => {
    const hoursAgo = (h: number) => new Date(Date.now() - h * 3_600_000).toISOString();
    recommended = { ...recommended, data: [{ ...job("fresh", 80), discovered_at: hoursAgo(23) }, { ...job("stale", 80), discovered_at: hoursAgo(25) }] };
    render(<RecommendedShort />);
    const [fresh, stale] = screen.getAllByRole("listitem");
    expect(within(fresh!).getByText("New today")).toBeInTheDocument();
    expect(within(stale!).queryByText("New today")).toBeNull();
  });

  it("uses plain words in the heading, and Tailor stays inside its own row", () => {
    render(<RecommendedShort />);
    expect(screen.getByRole("heading", { name: "Recommended for you" })).toBeInTheDocument();
    for (const li of screen.getAllByRole("listitem")) expect(within(li).getAllByRole("button", { name: "Tailor" })).toHaveLength(1);
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
    expect(screen.getByRole("button", { name: "Not interested in a" })).toHaveAttribute("data-icon-only", "yes");
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

  it("says so quietly and offers a 44px Try again that refetches", async () => {
    recommended = { data: [], isLoading: false, error: new Error("down"), isPaused: false, refetch };
    const user = userEvent.setup({ delay: null });
    render(<RecommendedShort />);
    expect(screen.getByText("We couldn't load recommended jobs right now.")).toBeInTheDocument();
    const retry = screen.getByRole("button", { name: "Try again" });
    expect(retry.className).toMatch(/max-md:min-h-11/);
    await user.click(retry);
    expect(refetch).toHaveBeenCalledTimes(1);
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

  it("uses the page's shared starter when given one, so one lock covers the card and the rows", async () => {
    const user = userEvent.setup({ delay: null });
    const start = vi.fn().mockResolvedValue(undefined);
    recommended = { ...recommended, data: [job("a", 80)] };
    render(<RecommendedShort starter={{ start, pickedId: null, error: null, failedJobId: null }} />);
    await user.click(screen.getByRole("button", { name: "Tailor" }));
    expect(start).toHaveBeenCalledWith(expect.objectContaining({ id: "a" }));
    expect(mutateAsync).not.toHaveBeenCalled();
  });

  it("disables every Tailor while the shared starter is busy", () => {
    recommended = { ...recommended, data: [job("a", 80), job("b", 80)] };
    render(<RecommendedShort starter={{ start: vi.fn(), pickedId: "zzz", error: null, failedJobId: null }} />);
    for (const b of screen.getAllByRole("button", { name: "Tailor" })) expect(b).toBeDisabled();
  });

  it("does not repeat an error that the next-step card already shows", () => {
    const error = { message: "Could not start", next: "retry" } as never;
    recommended = { ...recommended, data: [job("a", 80)] };
    const { rerender } = render(<RecommendedShort starter={{ start: vi.fn(), pickedId: null, error, failedJobId: "a" }} hideErrorFor="a" />);
    expect(screen.queryByRole("alert")).toBeNull();
    rerender(<RecommendedShort starter={{ start: vi.fn(), pickedId: null, error, failedJobId: "a" }} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Could not start");
  });
});
