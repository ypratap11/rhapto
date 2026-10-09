import { act, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/client";
import { writeConfirmedTrack, writeProposal } from "@/lib/coach/storage";
import { Coach } from "./Coach";

const server = {
  me: { data: { user_id: "u1" }, isLoading: false, error: null } as { data?: { user_id: string }; isLoading: boolean; error: Error | null },
  doc: null as { filename: string } | null,
  tracks: [] as { id: string; name: string }[],
  task: undefined as { progress: { request: { job_id: string } } } | undefined,
};
const search = { value: "" };
// vi.mock factories are hoisted above the module body, so what they close over must be hoisted too.
const { seen, stub } = vi.hoisted(() => {
  const seen: Record<string, Record<string, unknown>> = {};
  const stub = (name: string) => {
    const Stub = (props: Record<string, unknown>) => {
      seen[name] = props;
      return <div data-testid={name} />;
    };
    Stub.displayName = name;
    return Stub;
  };
  return { seen, stub };
});
const replace = vi.fn();
const tailorMutate = vi.fn();
const fire = vi.fn<(step: string) => Promise<void>>(async () => undefined);

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(search.value),
  useRouter: () => ({ replace }),
}));
vi.mock("@/lib/coach/events", () => ({ fireCoachEvent: (step: string) => fire(step) }));
vi.mock("@/lib/api/queries", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/queries")>()),
  useMe: () => server.me,
  useResumeDocument: () => ({ data: server.doc, isLoading: false, isFetched: true }),
  useTracks: () => ({ data: server.tracks, isLoading: false, isFetched: true }),
  useTailor: () => ({ mutateAsync: tailorMutate }),
  useTask: () => ({ data: server.task }),
}));
vi.mock("./UploadStep", () => ({ UploadStep: stub("upload") }));
vi.mock("./RoleStep", () => ({ RoleStep: stub("role") }));
vi.mock("./MatchesStep", () => ({ MatchesStep: stub("matches") }));
vi.mock("./PasteJob", () => ({ PasteJob: stub("paste") }));
vi.mock("./TailorStep", () => ({ TailorStep: stub("tailor") }));
vi.mock("./ResultStep", () => ({ ResultStep: stub("result") }));

beforeEach(() => {
  Object.assign(server, { me: { data: { user_id: "u1" }, isLoading: false, error: null }, doc: null, tracks: [], task: undefined });
  search.value = "";
  replace.mockReset();
  tailorMutate.mockReset();
  fire.mockClear();
  for (const k of Object.keys(seen)) delete seen[k];
  window.sessionStorage.clear();
  window.localStorage.clear();
});

describe("Coach: where it starts (server state wins)", () => {
  it("no stored document -> upload", () => {
    render(<Coach />);
    expect(screen.getByTestId("upload")).toBeInTheDocument();
  });

  it("a returning tester with tracks but no document starts at upload, not at the matches", () => {
    server.tracks = [{ id: "a", name: "A" }];
    render(<Coach />);
    expect(screen.getByTestId("upload")).toBeInTheDocument();
  });

  it("reload_between_upload_and_role_does_not_import_again: the cached proposal feeds the role step", () => {
    server.doc = { filename: "Maya_Chen_Resume.docx" };
    const proposal = { tracks: [{ id: "tpm", name: "Technical Program Manager", field: "f", role: "r", keywords: [] }], location: { location_home: null, location_preferred: [], remote_ok: null } };
    writeProposal("u1", proposal);
    render(<Coach />);
    expect(screen.getByTestId("role")).toBeInTheDocument();
    expect(screen.queryByTestId("upload")).toBeNull(); // nothing mounted that could import
    expect(seen.role!.proposal).toEqual(proposal);
  });

  it("document, no track, no cached proposal -> the role picker alone", () => {
    server.doc = { filename: "x.docx" };
    render(<Coach />);
    expect(seen.role!.proposal).toBeNull();
  });

  it("document and tracks -> the matches for the coach's last confirmed track", () => {
    server.doc = { filename: "x.docx" };
    server.tracks = [{ id: "a", name: "A" }, { id: "b", name: "B" }];
    writeConfirmedTrack("u1", "b");
    render(<Coach />);
    expect(screen.getByTestId("matches")).toBeInTheDocument();
    expect(seen.matches).toMatchObject({ trackId: "b", roleName: "B" });
  });

  it("reload_with_task_in_the_url_reattaches", () => {
    server.doc = { filename: "x.docx" };
    server.tracks = [{ id: "a", name: "A" }];
    search.value = "task=t42";
    render(<Coach />);
    expect(screen.getByTestId("tailor")).toBeInTheDocument();
    expect(seen.tailor!.taskId).toBe("t42");
  });

  it("the URL step is only a hint: ?step=4 with nothing stored still starts at upload", () => {
    search.value = "step=4";
    render(<Coach />);
    expect(screen.getByTestId("upload")).toBeInTheDocument();
  });

  it("a task in the URL with a step hint but no tracks goes to the role step, never the matches", () => {
    server.doc = { filename: "x.docx" };
    search.value = "task=t42&step=4";
    render(<Coach />);
    expect(screen.getByTestId("role")).toBeInTheDocument();
    expect(screen.queryByTestId("matches")).toBeNull();
  });

  it("fires 'started' once", () => {
    const { rerender } = render(<Coach />);
    rerender(<Coach />);
    expect(fire.mock.calls.filter(([s]) => s === "started")).toHaveLength(1);
  });
});

describe("Coach: before it can start", () => {
  it("the loading screen carries the way out", () => {
    server.me = { data: undefined, isLoading: true, error: null };
    render(<Coach />);
    expect(screen.getByRole("status")).toHaveTextContent(/getting things ready/i);
    expect(screen.getByRole("link", { name: /skip to the full app/i })).toHaveAttribute("href", "/dashboard");
  });

  it("a failed /me is a plain error with the way out, not an endless spinner", () => {
    server.me = { data: undefined, isLoading: false, error: new TypeError("Failed to fetch") };
    render(<Coach />);
    expect(screen.getByRole("alert")).toHaveTextContent("Something went wrong on our side. Try again in a moment.");
    expect(screen.queryByText(/getting things ready/i)).toBeNull();
    expect(screen.getByRole("link", { name: /skip to the full app/i })).toHaveAttribute("href", "/dashboard");
  });
});

describe("Coach: the flow", () => {
  const start = () => {
    server.doc = { filename: "x.docx" };
    server.tracks = [{ id: "a", name: "A" }];
    render(<Coach />);
  };

  it("starting a tailor runs tune mode, puts the task in the URL, fires the event and moves to the tailor step", async () => {
    start();
    tailorMutate.mockResolvedValueOnce({ id: "t1", status: "running" });
    await (seen.matches!.onTailor as (job: { id: string }) => Promise<void>)({ id: "j1" });
    expect(tailorMutate).toHaveBeenCalledWith({ jobId: "j1", body: { mode: "tune" } });
    expect(replace).toHaveBeenCalledWith("/start?task=t1");
    expect(fire).toHaveBeenCalledWith("tailor_started");
    await waitFor(() => expect(screen.getByTestId("tailor")).toBeInTheDocument());
    expect(seen.tailor!.taskId).toBe("t1");
  });

  it("a refused start is a plain error on the matches, never a thrown rejection", async () => {
    start();
    tailorMutate.mockRejectedValueOnce(new ApiError(409, { title: "x", status: 409, code: "trial_limit_reached", detail: "You have used all 3 free tailoring runs on this instance. Add your own provider API key in Settings to keep going." }, "x"));
    await expect((seen.matches!.onTailor as (job: { id: string }) => Promise<void>)({ id: "j1" })).resolves.toBeUndefined();
    await waitFor(() => expect((seen.matches!.error as { next: string } | null)?.next).toBe("settings"));
    expect(replace).not.toHaveBeenCalled();
    expect(fire).not.toHaveBeenCalledWith("tailor_started");
  });

  it("finishing a run shows the result for that package", async () => {
    start();
    tailorMutate.mockResolvedValueOnce({ id: "t1", status: "running" });
    await (seen.matches!.onTailor as (job: { id: string }) => Promise<void>)({ id: "j1" });
    await waitFor(() => expect(screen.getByTestId("tailor")).toBeInTheDocument());
    (seen.tailor!.onDone as (id: string) => void)("pk1");
    await waitFor(() => expect(screen.getByTestId("result")).toBeInTheDocument());
    expect(seen.result!.packageId).toBe("pk1");
  });

  it("'Try another' returns to the matches and clears the task from the URL", async () => {
    start();
    tailorMutate.mockResolvedValueOnce({ id: "t1", status: "running" });
    await (seen.matches!.onTailor as (job: { id: string }) => Promise<void>)({ id: "j1" });
    await waitFor(() => expect(screen.getByTestId("tailor")).toBeInTheDocument());
    (seen.tailor!.onPickAnother as () => void)();
    await waitFor(() => expect(screen.getByTestId("matches")).toBeInTheDocument());
    expect(replace).toHaveBeenLastCalledWith("/start");
  });

  it("a blocked package's retry starts a FRESH tune run on the same job (no parent_package_id) and follows the new task", async () => {
    start();
    tailorMutate.mockResolvedValueOnce({ id: "t1", status: "running" });
    await (seen.matches!.onTailor as (job: { id: string }) => Promise<void>)({ id: "j1" });
    await waitFor(() => expect(screen.getByTestId("tailor")).toBeInTheDocument());
    (seen.tailor!.onDone as (id: string) => void)("pk1");
    await waitFor(() => expect(screen.getByTestId("result")).toBeInTheDocument());
    tailorMutate.mockResolvedValueOnce({ id: "t2", status: "running" });
    (seen.result!.onRetry as (pkg: { id: string; job_id: string }) => void)({ id: "pk1", job_id: "j1" });
    await waitFor(() => expect(tailorMutate).toHaveBeenLastCalledWith({ jobId: "j1", body: { mode: "tune" } }));
    await waitFor(() => expect(replace).toHaveBeenLastCalledWith("/start?task=t2"));
  });

  it("a double tap on a failed run's 'Try again' starts exactly one run", async () => {
    start();
    tailorMutate.mockResolvedValueOnce({ id: "t1", status: "running" });
    await (seen.matches!.onTailor as (job: { id: string }) => Promise<void>)({ id: "j1" });
    await waitFor(() => expect(screen.getByTestId("tailor")).toBeInTheDocument());
    tailorMutate.mockClear();
    let finish: (v: { id: string; status: string }) => void = () => undefined;
    tailorMutate.mockImplementationOnce(() => new Promise((resolve) => { finish = resolve; }));
    const retry = seen.tailor!.onRetry as () => Promise<void>;
    const first = retry();
    const second = retry();
    await act(async () => { finish({ id: "t2", status: "running" }); await Promise.all([first, second]); });
    expect(tailorMutate).toHaveBeenCalledTimes(1);
    expect(tailorMutate).toHaveBeenCalledWith({ jobId: "j1", body: { mode: "tune" } });
  });

  it("pasting a job starts a tailor for it, and Cancel returns", async () => {
    start();
    (seen.matches!.onPaste as () => void)();
    await waitFor(() => expect(screen.getByTestId("paste")).toBeInTheDocument());
    tailorMutate.mockResolvedValueOnce({ id: "t3", status: "running" });
    await (seen.paste!.onJob as (id: string) => Promise<void>)("job-7");
    expect(tailorMutate).toHaveBeenCalledWith({ jobId: "job-7", body: { mode: "tune" } });
    await waitFor(() => expect(screen.getByTestId("tailor")).toBeInTheDocument());
  });
});

describe("Coach: confirming a role", () => {
  it("moves from the role step to the matches for that track", async () => {
    server.doc = { filename: "x.docx" };
    render(<Coach />);
    expect(screen.getByTestId("role")).toBeInTheDocument();
    (seen.role!.onConfirmed as (r: { id: string; name: string }) => void)({ id: "tpm", name: "TPM" });
    await waitFor(() => expect(screen.getByTestId("matches")).toBeInTheDocument());
    expect(seen.matches).toMatchObject({ trackId: "tpm", roleName: "TPM" });
  });

  it("moves from the upload step to the role step, carrying the proposal and any import error", async () => {
    render(<Coach />);
    const proposal = { tracks: [], location: { location_home: null, location_preferred: [], remote_ok: null } };
    (seen.upload!.onDone as (r: unknown) => void)({ filename: "x.docx", proposal, importError: { message: "m", next: "role-picker" } });
    await waitFor(() => expect(screen.getByTestId("role")).toBeInTheDocument());
    expect(seen.role).toMatchObject({ proposal, importError: { message: "m" } });
  });
});
