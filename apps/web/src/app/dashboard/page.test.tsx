import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/client";
import DashboardPage from "./page";

vi.mock("@/components/dashboard/ApplicationsSection", () => ({
  ApplicationsSection: ({
    rows,
    chip,
    onChipChange,
    onSelect,
  }: {
    rows: unknown[];
    chip: string;
    onChipChange: (c: string) => void;
    onSelect: (id: string) => void;
  }) => (
    <div>
      <h2 id="applications-heading">Your applications</h2>
      <p>applications:{rows.length}</p>
      <p>chip:{chip}</p>
      <button onClick={() => onChipChange("all")}>reset-chip</button>
      <button onClick={() => onSelect("a2")}>open-a2</button>
    </div>
  ),
}));
vi.mock("@/components/dashboard/RecommendedShort", () => ({
  RecommendedShort: ({ hideErrorFor }: { hideErrorFor?: string | null }) => <div>recommended hide:{hideErrorFor ?? "none"}</div>,
}));
vi.mock("@/components/dashboard/FinishSetupLine", () => ({ FinishSetupLine: () => <div>finish-setup</div> }));
vi.mock("@/components/pipeline/ApplicationSheet", () => ({
  ApplicationSheet: ({ application }: { application: { id: string } | null }) => <div>sheet:{application?.id ?? "closed"}</div>,
}));
const start = vi.fn();
vi.mock("@/lib/coach/useStartTailor", () => ({ useStartTailor: () => ({ start, pickedId: null, error: null, failedJobId: null }) }));

type Q = { data: unknown; error: unknown; isLoading: boolean; isPaused: boolean };
let applications: Q;
let resume: Q;
let dashboard: Q;
let answers: Q;
let tracks: Q;
let recommended: Q;
let drafts: Q;
let draftsEnabled: boolean | undefined;
vi.mock("@/lib/api/queries", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/queries")>()),
  useApplications: () => applications,
  useResumeDocument: () => resume,
  useDashboard: () => dashboard,
  useAnswers: () => answers,
  useTracks: () => tracks,
  useRecommendedJobs: () => recommended,
  usePackageList: (_filter: string, enabled?: boolean) => {
    draftsEnabled = enabled;
    return drafts;
  },
}));

const settled = (data: unknown): Q => ({ data, error: null, isLoading: false, isPaused: false });
const loadingQ: Q = { data: undefined, error: null, isLoading: true, isPaused: false };
const columns = (rows: object[]) => ({ columns: { all: rows } });
const app = (id: string, status: string, company = `Co ${id}`) => ({ id, status, job: { company, title: "TPM" } });
const job = (id: string, fit: number, track = "t1") => ({ id, title: `Role ${id}`, company: `Firm ${id}`, best_fit: fit, best_track_id: track });
const dash = (over: object = {}) => settled({ needs_review_count: 0, checklist: {}, due_followups: [], ...over });
const draft = { id: "p1", job_id: "j1", company: "Rigetti", title: "Senior TPM", best_fit: 78 };

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date(2026, 9, 11, 15, 0, 0)); // 3pm local
  start.mockReset();
  applications = settled(columns([]));
  resume = settled({ filename: "cv.docx" });
  dashboard = dash();
  answers = settled({ name: "Maya Rao" });
  tracks = settled([{ id: "t1", min_fit: 70 }]);
  recommended = settled([]);
  drafts = settled([draft]);
  draftsEnabled = undefined;
});
afterEach(() => vi.useRealTimers());

const tile = (name: RegExp) => {
  const found = [...screen.queryAllByRole("link", { name }), ...screen.queryAllByRole("button", { name })];
  if (found.length !== 1) throw new Error(`expected one tile ${name}, found ${found.length}`);
  return found[0]!;
};

describe("greeting", () => {
  it("greets by the browser hour and first name", () => {
    render(<DashboardPage />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Good afternoon, Maya");
  });

  it("changes at the hour boundaries", () => {
    vi.setSystemTime(new Date(2026, 9, 11, 11, 59, 0));
    const { unmount } = render(<DashboardPage />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Good morning, Maya");
    unmount();
    vi.setSystemTime(new Date(2026, 9, 11, 18, 0, 0));
    render(<DashboardPage />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Good evening, Maya");
  });

  it("says Welcome back with no name, or when the name can't be read", () => {
    answers = settled({});
    const { unmount } = render(<DashboardPage />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Welcome back");
    unmount();
    answers = { data: undefined, error: new Error("x"), isLoading: false, isPaused: false };
    render(<DashboardPage />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Welcome back");
  });

  it("holds the name slot while the profile loads, so it doesn't flash Welcome back", () => {
    answers = loadingQ;
    render(<DashboardPage />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Dashboard");
    expect(screen.queryByText("Welcome back")).toBeNull();
  });
});

describe("summary line", () => {
  it("says both clauses from real counts, counting only the rows shown", () => {
    dashboard = dash({ needs_review_count: 1 });
    recommended = settled([job("1", 80), job("2", 70), job("3", 69), job("4", 90), job("5", 71)]);
    render(<DashboardPage />);
    expect(screen.getByText("4 strong matches are waiting, and 1 resume is ready for your review.")).toBeInTheDocument();
  });

  it("leaves out a clause whose count is zero", () => {
    dashboard = dash({ needs_review_count: 2 });
    recommended = settled([job("1", 10)]);
    render(<DashboardPage />);
    expect(screen.getByText("2 resumes are ready for your review.")).toBeInTheDocument();
  });

  it("falls back when both are zero", () => {
    render(<DashboardPage />);
    expect(screen.getByText("Here's where your search stands.")).toBeInTheDocument();
  });

  it("does not claim a review count when the dashboard failed to load", () => {
    dashboard = { data: undefined, error: new ApiError(500, null, "boom"), isLoading: false, isPaused: false };
    recommended = settled([job("1", 90)]);
    render(<DashboardPage />);
    expect(screen.getByText("1 strong match is waiting.")).toBeInTheDocument();
    expect(screen.queryByText(/ready for your review/)).toBeNull();
  });

  it("waits for the tracks before counting strong matches", () => {
    tracks = loadingQ;
    recommended = settled([job("1", 90)]);
    render(<DashboardPage />);
    expect(screen.queryByText(/strong match/)).toBeNull();
    expect(screen.queryByText("Here's where your search stands.")).toBeNull();
  });
});

describe("next step", () => {
  it("1: review the newest draft, linking to its page", () => {
    dashboard = dash({ needs_review_count: 1, due_followups: [{ application_id: "a1", follow_up_at: "2026-10-01T00:00:00Z", job: { company: "Sunrun", title: "PM" } }] });
    applications = settled(columns([app("a1", "applied", "Sunrun")]));
    recommended = settled([job("1", 90)]);
    render(<DashboardPage />);
    expect(screen.getByText("Review your Rigetti resume")).toBeInTheDocument();
    expect(screen.getByText("Senior TPM · fit 78")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Review it" })).toHaveAttribute("href", "/jobs/j1/packages/p1");
    expect(draftsEnabled).toBe(true);
  });

  it("2: a due follow-up opens that application's sheet", async () => {
    const user = userEvent.setup({ delay: null });
    dashboard = dash({ due_followups: [{ application_id: "a1", follow_up_at: "2026-10-01T00:00:00Z", job: { company: "Sunrun", title: "PM" } }] });
    applications = settled(columns([app("a1", "applied", "Sunrun")]));
    recommended = settled([job("1", 90)]);
    render(<DashboardPage />);
    expect(screen.getByText("Follow up with Sunrun")).toBeInTheDocument();
    expect(screen.getByText("sheet:closed")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Update status" }));
    expect(screen.getByText("sheet:a1")).toBeInTheDocument();
    expect(draftsEnabled).toBe(false);
  });

  it("2: finds the application in the unfiltered board, and skips one that is not there", () => {
    dashboard = dash({
      due_followups: [
        { application_id: "ghost", follow_up_at: "2026-10-01T00:00:00Z", job: { company: "Ghost", title: "x" } },
        { application_id: "q1", follow_up_at: "2026-10-01T00:00:00Z", job: { company: "Queued Co", title: "y" } },
      ],
    });
    applications = settled(columns([app("q1", "queued", "Queued Co")]));
    render(<DashboardPage />);
    expect(screen.queryByText("Follow up with Ghost")).toBeNull();
    expect(screen.getByText("Follow up with Queued Co")).toBeInTheDocument();
  });

  it("2: ignores a follow-up that is not due yet", () => {
    dashboard = dash({ due_followups: [{ application_id: "a1", follow_up_at: "2026-12-01T00:00:00Z", job: { company: "Sunrun", title: "PM" } }] });
    applications = settled(columns([app("a1", "applied", "Sunrun")]));
    render(<DashboardPage />);
    expect(screen.queryByText(/Follow up with/)).toBeNull();
  });

  it("3: tailor the top recommended job, through the shared starter", async () => {
    const user = userEvent.setup({ delay: null });
    recommended = settled([job("1", 90), job("2", 80)]);
    render(<DashboardPage />);
    expect(screen.getByText("Tailor a resume for Firm 1")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Tailor a resume for Firm 1" }));
    expect(start).toHaveBeenCalledWith(expect.objectContaining({ id: "1" }));
    expect(screen.getByText("recommended hide:1")).toBeInTheDocument();
  });

  it("4: no card when there is nothing to suggest", () => {
    render(<DashboardPage />);
    expect(screen.queryByRole("region", { name: "Next step" })).toBeNull();
    expect(screen.getByText("recommended hide:none")).toBeInTheDocument();
  });

  it("does not fall through to Tailor while the draft list loads", () => {
    dashboard = dash({ needs_review_count: 1 });
    drafts = loadingQ;
    recommended = settled([job("1", 90)]);
    render(<DashboardPage />);
    expect(screen.queryByText(/Tailor a resume for/)).toBeNull();
    expect(screen.queryByText(/Review your/)).toBeNull();
  });

  it("links to the review tab when the draft list fails", () => {
    dashboard = dash({ needs_review_count: 3 });
    drafts = { data: undefined, error: new Error("x"), isLoading: false, isPaused: false };
    recommended = settled([job("1", 90)]);
    render(<DashboardPage />);
    expect(screen.getByRole("link", { name: "Review them" })).toHaveAttribute("href", "/resumes?tab=review");
    expect(screen.queryByText(/Tailor a resume for/)).toBeNull();
  });
});

describe("tiles", () => {
  const board = columns([
    app("a1", "applied"),
    app("a2", "screen"),
    app("i1", "interview"),
    app("o1", "offer"),
    app("c1", "closed"),
    app("d1", "discovered"),
  ]);

  it("shows the counts, with applied including screening and closed left out", () => {
    dashboard = dash({ needs_review_count: 4 });
    applications = settled(board);
    render(<DashboardPage />);
    expect(tile(/To review/)).toHaveTextContent("4");
    expect(tile(/To review/)).toHaveAttribute("href", "/resumes?tab=review");
    expect(tile(/^2\s*Applied/)).toBeInTheDocument();
    expect(tile(/^1\s*Interviewing/)).toBeInTheDocument();
    expect(tile(/^1\s*Offers/)).toBeInTheDocument();
    expect(screen.getByText("applications:5")).toBeInTheDocument();
  });

  it("sets the applications filter, and a second press clears it", async () => {
    const user = userEvent.setup({ delay: null });
    applications = settled(board);
    render(<DashboardPage />);
    expect(screen.getByText("chip:all")).toBeInTheDocument();
    await user.click(tile(/Interviewing/));
    expect(screen.getByText("chip:interviewing")).toBeInTheDocument();
    expect(tile(/Interviewing/)).toHaveAttribute("aria-pressed", "true");
    await user.click(tile(/Applied/));
    expect(screen.getByText("chip:applied")).toBeInTheDocument();
    expect(tile(/Interviewing/)).toHaveAttribute("aria-pressed", "false");
    await user.click(tile(/Applied/));
    expect(screen.getByText("chip:all")).toBeInTheDocument();
  });

  it("lets the list reset the filter and open a row's sheet", async () => {
    const user = userEvent.setup({ delay: null });
    applications = settled(board);
    render(<DashboardPage />);
    await user.click(tile(/Offers/));
    await user.click(screen.getByRole("button", { name: "reset-chip" }));
    expect(screen.getByText("chip:all")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "open-a2" }));
    expect(screen.getByText("sheet:a2")).toBeInTheDocument();
  });

  it("scrolls to the applications on a phone-width layout", async () => {
    const user = userEvent.setup({ delay: null });
    const scroll = vi.fn();
    Element.prototype.scrollIntoView = scroll;
    const mm = vi.fn((q: string) => ({ matches: q.includes("max-width"), media: q }));
    window.matchMedia = mm as never;
    applications = settled(board);
    render(<DashboardPage />);
    await user.click(tile(/Offers/));
    expect(scroll).toHaveBeenCalled();
    delete (window as { matchMedia?: unknown }).matchMedia;
  });

  it("shows quiet zeros and the empty sentence when there are no applications", () => {
    render(<DashboardPage />);
    expect(within(tile(/Applied/)).getByText("0").className).toContain("text-muted-foreground");
    expect(screen.getByText("Nothing sent yet")).toBeInTheDocument();
    expect(
      screen.getByText("Your applications will show here. After you tailor a resume and send it, mark it as applied and track replies here."),
    ).toBeInTheDocument();
    expect(screen.queryByText(/^applications:/)).toBeNull();
    expect(screen.getByText("recommended hide:none")).toBeInTheDocument();
  });

  it("does not show an untrue 0 when the dashboard failed", () => {
    dashboard = { data: undefined, error: new ApiError(500, null, "boom"), isLoading: false, isPaused: false };
    render(<DashboardPage />);
    expect(tile(/To review/)).toHaveTextContent("–");
    expect(tile(/To review/)).toHaveTextContent("Couldn't load");
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });
});

describe("states", () => {
  it("shows skeletons, no tiles, columns or empty copy while loading", () => {
    applications = loadingQ;
    render(<DashboardPage />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Good afternoon, Maya");
    expect(screen.queryByText(/^applications:/)).toBeNull();
    expect(screen.queryByText(/^recommended/)).toBeNull();
    expect(screen.queryByText("Start with your resume")).toBeNull();
    expect(screen.queryByText(/your applications will show here/i)).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(document.querySelectorAll('[data-slot="skeleton"]').length).toBeGreaterThan(4);
  });

  it("asks a brand-new person to upload a resume, with no tiles or columns", () => {
    resume = settled(null);
    render(<DashboardPage />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Good afternoon, Maya");
    expect(screen.getByText("Start with your resume")).toBeInTheDocument();
    expect(screen.getByText("Upload a Word (.docx) file. Your tailored resumes are built from what's in it.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Upload resume" })).toHaveAttribute("href", "/start");
    expect(screen.queryByText(/^recommended/)).toBeNull();
    expect(screen.queryByText("To review")).toBeNull();
    expect(screen.queryByText("finish-setup")).toBeNull();
  });

  it("does not count discovered or queued jobs as applications", () => {
    applications = settled(columns([app("1", "discovered"), app("2", "queued")]));
    render(<DashboardPage />);
    expect(screen.queryByText(/^applications:/)).toBeNull();
  });

  it("still shows applications from the older flow when there is no resume", () => {
    resume = settled(null);
    applications = settled(columns([app("1", "applied")]));
    render(<DashboardPage />);
    expect(screen.getByText("applications:1")).toBeInTheDocument();
    expect(screen.queryByText("Start with your resume")).toBeNull();
  });

  it("shows the finish-setup line right under the hero", () => {
    render(<DashboardPage />);
    expect(screen.getByText("finish-setup")).toBeInTheDocument();
  });

  it("shows the error banner and keeps the columns when a query fails", () => {
    applications = { data: columns([app("1", "applied")]), error: new ApiError(500, null, "Server error"), isLoading: false, isPaused: false };
    render(<DashboardPage />);
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByText("applications:1")).toBeInTheDocument();
    expect(screen.getByText(/^recommended/)).toBeInTheDocument();
  });

  it("does not call a paused query an empty one", () => {
    resume = settled(null);
    applications = { data: undefined, error: null, isLoading: false, isPaused: true };
    render(<DashboardPage />);
    expect(screen.queryByText("Start with your resume")).toBeNull();
    expect(screen.getByRole("alert")).toHaveTextContent(/can.t reach rhapto.s api/i);
  });

  it("keeps one application sheet on the page", () => {
    render(<DashboardPage />);
    expect(screen.getAllByText(/^sheet:/)).toHaveLength(1);
  });
});
