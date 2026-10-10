import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { JobOut } from "@/lib/api/queries";
import * as copy from "@/lib/coach/copy";
import type { MatchesState } from "@/lib/coach/matches";
import { MatchesStep } from "./MatchesStep";

const matches: { state: MatchesState } = { state: { kind: "loading", offerPaste: false } };
const fire = vi.fn<(step: string) => Promise<undefined>>(async () => undefined);
vi.mock("@/lib/coach/events", () => ({ fireCoachEvent: (step: string) => fire(step) }));
vi.mock("@/lib/coach/matches", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/coach/matches")>()),
  useCoachMatches: () => matches,
}));
const runsLeft = { value: 3 as number | null };
vi.mock("@/lib/api/queries", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/queries")>()),
  useTracks: () => ({ data: [{ id: "tpm", name: "Technical Program Manager", min_fit: 60 }] }),
  useDashboard: () => ({ data: { checklist: { trial_runs_left: runsLeft.value } } }),
}));
// "Show other jobs" runs its own query; these tests never open it, and no QueryClientProvider is mounted.
vi.mock("@tanstack/react-query", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@tanstack/react-query")>()),
  useQuery: () => ({ data: undefined }),
}));

const job = (id: string, fit: number, title = `Role ${id}`) => ({ id, title, company: "ExampleCo", best_fit: fit, best_track_id: "tpm" }) as unknown as JobOut;
const base = { trackId: "tpm", roleName: "Technical Program Manager", error: null, onPaste: vi.fn() };

beforeEach(() => {
  fire.mockClear();
  runsLeft.value = 3;
  matches.state = { kind: "loading", offerPaste: false };
});

describe("MatchesStep", () => {
  it("shows the waiting title and no paste option before the threshold", () => {
    render(<MatchesStep {...base} onTailor={vi.fn()} />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(/finding your best matches/i);
    expect(screen.queryByRole("button", { name: /paste a job/i })).toBeNull();
  });

  it("tells the tester the wait is a minute or two", () => {
    render(<MatchesStep {...base} onTailor={vi.fn()} />);
    expect(screen.getByRole("status")).toHaveTextContent("This can take a minute or two.");
  });

  it("offers 'Paste a job you like instead' once the wait is long, and keeps showing that it is still looking", async () => {
    matches.state = { kind: "waiting", offerPaste: true };
    const onPaste = vi.fn();
    render(<MatchesStep {...base} onPaste={onPaste} onTailor={vi.fn()} />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(/finding your best matches/i);
    await userEvent.setup({ delay: null }).click(screen.getByRole("button", { name: /paste a job you like instead/i }));
    expect(onPaste).toHaveBeenCalled();
  });

  it("ready: cards with a plain label (Strong at or above min_fit, otherwise Good), no raw number, runs left, jobs_shown once", () => {
    matches.state = { kind: "ready", jobs: [job("a", 71), job("b", 46)], final: true };
    const { rerender } = render(<MatchesStep {...base} onTailor={vi.fn()} />);
    const cards = screen.getAllByRole("listitem");
    expect(cards[0]).toHaveTextContent("Role a");
    expect(cards[0]).toHaveTextContent("Strong match");
    expect(cards[1]).toHaveTextContent("Good match");
    expect(within(cards[0]!).getByText("Strong match").className).toContain("bg-fit-high-bg");
    expect(within(cards[1]!).getByText("Good match").className).toContain("bg-surface-muted");
    expect(document.body.textContent).not.toMatch(/\b71\b|\b46\b/);
    expect(screen.getByText("3 free runs left")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /paste a job instead/i })).toBeInTheDocument();
    rerender(<MatchesStep {...base} onTailor={vi.fn()} />);
    expect(fire.mock.calls.filter(([s]) => s === "jobs_shown")).toHaveLength(1);
  });

  it("partial rows show at once, say more are coming, and can already be tailored", async () => {
    matches.state = { kind: "ready", jobs: [job("a", 71)], final: false };
    const onTailor = vi.fn(async () => undefined);
    render(<MatchesStep {...base} onTailor={onTailor} />);
    expect(screen.getByRole("status")).toHaveTextContent(/still finding more matches/i);
    await userEvent.setup({ delay: null }).click(screen.getByRole("button", { name: /tailor this one/i }));
    expect(onTailor).toHaveBeenCalledTimes(1);
    expect(fire).toHaveBeenCalledWith("jobs_shown");
  });

  it("shows the shared coach copy", () => {
    matches.state = { kind: "ready", jobs: [job("a", 71)], final: true };
    render(<MatchesStep {...base} onTailor={vi.fn()} />);
    expect(screen.getByRole("heading", { level: 1, name: copy.matchesTitle("Technical Program Manager") })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: copy.TAILOR_THIS })).toBeInTheDocument();
  });

  it("a final list does not say more are coming", () => {
    matches.state = { kind: "ready", jobs: [job("a", 71)], final: true };
    render(<MatchesStep {...base} onTailor={vi.fn()} />);
    expect(screen.queryByText(/still finding more/i)).toBeNull();
  });

  it("shows no runs line when no cap applies", () => {
    runsLeft.value = null;
    matches.state = { kind: "ready", jobs: [job("a", 71)], final: true };
    render(<MatchesStep {...base} onTailor={vi.fn()} />);
    expect(screen.queryByText(/free run/i)).toBeNull();
  });

  it("tailor_this_one_starts_one_task_on_a_double_click, and every button is disabled meanwhile", async () => {
    matches.state = { kind: "ready", jobs: [job("a", 71), job("b", 66)], final: true };
    let release: () => void = () => undefined;
    const onTailor = vi.fn<(job: JobOut) => Promise<void>>(() => new Promise<void>((resolve) => { release = resolve; }));
    render(<MatchesStep {...base} onTailor={onTailor} />);
    const user = userEvent.setup({ delay: null });
    const buttons = screen.getAllByRole("button", { name: /tailor this one/i });
    await user.dblClick(buttons[0]!);
    expect(onTailor).toHaveBeenCalledTimes(1);
    expect(onTailor.mock.calls[0]![0]).toMatchObject({ id: "a" });
    await waitFor(() => expect(screen.getAllByRole("button", { name: /tailor this one|starting/i }).every((b) => (b as HTMLButtonElement).disabled)).toBe(true));
    release();
    await waitFor(() => expect(screen.getAllByRole("button", { name: /tailor this one/i })[0]).not.toBeDisabled());
  });

  it("two clicks fired in the same tick start one task (the ref lock, not the disabled state, stops the second)", async () => {
    matches.state = { kind: "ready", jobs: [job("a", 71)], final: true };
    const onTailor = vi.fn<(job: JobOut) => Promise<void>>(() => new Promise<void>(() => undefined));
    render(<MatchesStep {...base} onTailor={onTailor} />);
    const button = screen.getAllByRole("button", { name: /tailor this one/i })[0]!;
    // Both events are dispatched before React can re-render the disabled state.
    const fireBoth = () => {
      button.click();
      button.click();
    };
    act(() => {
      // batch both clicks inside one act so no render happens between them
      fireBoth();
    });
    expect(onTailor).toHaveBeenCalledTimes(1);
  });

  it("an error from starting is shown in plain words and the buttons come back", () => {
    matches.state = { kind: "ready", jobs: [job("a", 71)], final: true };
    render(<MatchesStep {...base} error={{ message: "Rhapto isn't set up to tailor yet", next: "feedback", link: { label: "Tell us", href: "/feedback" } }} onTailor={vi.fn()} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Rhapto isn't set up to tailor yet");
    expect(screen.getByRole("link", { name: "Tell us" })).toHaveAttribute("href", "/feedback");
  });

  it("no_jobs: says why and offers to paste a job", () => {
    matches.state = { kind: "none", reason: "no_jobs" };
    render(<MatchesStep {...base} onTailor={vi.fn()} />);
    expect(screen.getByText(/don't have any jobs to show yet/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /paste a job/i })).toBeInTheDocument();
  });

  it("no strong matches: names the role, offers Paste a job and Show other jobs", () => {
    matches.state = { kind: "none", reason: "no_strong_matches" };
    render(<MatchesStep {...base} onTailor={vi.fn()} />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("No strong matches for Technical Program Manager yet");
    expect(screen.getByRole("button", { name: /paste a job/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /show other jobs/i })).toBeInTheDocument();
  });

  it("has the skip link", () => {
    render(<MatchesStep {...base} onTailor={vi.fn()} />);
    expect(screen.getByRole("link", { name: /back to your dashboard/i })).toHaveAttribute("href", "/dashboard");
  });
});
