import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, renderHook, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { toast } from "sonner";
import { TailorButton } from "./TailorButton";
import { ApiError } from "@/lib/api/client";
import { useTailoringCount } from "@/lib/tailoring";
import type { JobOut, MeOut, ResumeDocumentOut } from "@/lib/api/queries";

const mutateAsync = vi.fn();
let tracksData: { id: string; name: string; min_fit: number }[] = [];
// `undefined` data with `isPending` is what useQuery reports before the request settles.
let resumeDocumentData: ResumeDocumentOut | null | undefined = null;
let resumeDocumentPending = false;
let meData: MeOut | undefined;
vi.mock("@/lib/api/queries", () => ({
  useTracks: () => ({ data: tracksData }),
  useTailor: () => ({ mutateAsync, isPending: false }),
  useResumeDocument: () => ({ data: resumeDocumentData, isPending: resumeDocumentPending }),
  useMe: () => ({ data: meData }),
  invalidateJobs: vi.fn(),
}));
const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("./TaskProgress", () => ({
  TaskProgress: ({ taskId, onFinished }: { taskId: string; onFinished: () => void }) => (
    <div>
      progress:{taskId}
      <button onClick={onFinished}>finish</button>
    </div>
  ),
}));

const job: JobOut = {
  id: "j1",
  source: "manual",
  company: "ExampleCo",
  title: "Title",
  location: null,
  url: null,
  jd_text: "lorem",
  extracted: null,
  discovered_at: "2026-09-09T10:00:00Z",
  latest_package: null,
  application_status: null,
  rescued: false,
  also_ids: [],
  scores: [],
};

function renderButton(overrides: Partial<JobOut> = {}) {
  const client = new QueryClient();
  return render(
    <QueryClientProvider client={client}>
      <TailorButton job={{ ...job, ...overrides }} />
    </QueryClientProvider>,
  );
}

const lightRadio = () => screen.getByRole("radio", { name: "Light touch (keep my wording, change little)", hidden: true });
const fullRadio = () => screen.getByRole("radio", { name: "Full rewrite (rebuild from my experience)", hidden: true });

const resumeDocument: ResumeDocumentOut = {
  filename: "resume.docx",
  uploaded_at: "2026-09-01T00:00:00Z",
  document: { filename: "resume.docx", paragraphs: [], sections: [] },
};

describe("TailorButton", () => {
  beforeEach(() => {
    tracksData = [];
    resumeDocumentData = null;
    resumeDocumentPending = false;
    meData = { user_id: "u1", email: "dev@example.com", llm_configured: true, auth_mode: "token" };
    mutateAsync.mockReset();
    push.mockReset();
    vi.mocked(toast.error).mockReset();
  });

  it("shows no select or combobox by default and keeps Options closed", () => {
    tracksData = [{ id: "ai-pm", name: "AI PM", min_fit: 60 }];
    renderButton();
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Tailor my resume for this job" })).toBeInTheDocument();
    const details = screen.getByText("Options").closest("details");
    expect(details).not.toHaveAttribute("open");
  });

  it("offers the two modes as radios inside Options", () => {
    renderButton();
    expect(screen.getByRole("radio", { name: "Light touch (keep my wording, change little)", hidden: true })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "Full rewrite (rebuild from my experience)", hidden: true })).toBeInTheDocument();
  });

  it("hides the Goal select with one track and shows it with two, preselecting the best fit", () => {
    tracksData = [{ id: "ai-pm", name: "AI PM", min_fit: 60 }];
    const { unmount } = renderButton();
    expect(screen.queryByRole("combobox", { name: "Goal", hidden: true })).not.toBeInTheDocument();
    unmount();
    tracksData = [
      { id: "other", name: "Other Track", min_fit: 50 },
      { id: "ai-pm", name: "AI PM", min_fit: 60 },
    ];
    renderButton({ best_track_id: "ai-pm" });
    expect(screen.getByRole("combobox", { name: "Goal", hidden: true })).toBeInTheDocument();
    // Closed, the trigger shows the best-fit goal's name (never its id), not the first one.
    expect(screen.getByRole("combobox", { name: "Goal", hidden: true })).toHaveTextContent("AI PM");
    expect(screen.queryByText("ai-pm")).not.toBeInTheDocument();
  });

  it("renders TaskProgress even when the mutation returns an already-finished task", async () => {
    mutateAsync.mockResolvedValueOnce({
      id: "t1",
      status: "succeeded",
      result_ref: "p1",
      error: null,
      created_at: "2026-09-09T10:00:00Z",
      finished_at: "2026-09-09T10:01:00Z",
      progress: {},
      type: "tailor",
    });
    renderButton();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /^tailor/i }));

    expect(await screen.findByText("progress:t1")).toBeInTheDocument();
  });

  it("counts the job as tailoring only between start and finish", async () => {
    mutateAsync.mockResolvedValueOnce({
      id: "t1",
      status: "running",
      result_ref: null,
      error: null,
      created_at: "2026-09-09T10:00:00Z",
      finished_at: null,
      progress: {},
      type: "tailor",
    });
    const count = renderHook(() => useTailoringCount());
    expect(count.result.current).toBe(0);

    renderButton();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /^tailor/i }));
    await screen.findByText("progress:t1");
    expect(count.result.current).toBe(1);

    await user.click(screen.getByRole("button", { name: "finish" }));
    expect(count.result.current).toBe(0);
  });

  it("does not increment the count when the mutation fails", async () => {
    mutateAsync.mockRejectedValueOnce(new Error("boom"));
    const count = renderHook(() => useTailoringCount());
    expect(count.result.current).toBe(0);

    renderButton();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /^tailor/i }));
    await screen.findByRole("button", { name: /^tailor/i }); // still idle, no progress rendered

    expect(count.result.current).toBe(0);
  });

  it("stops counting the job if the button unmounts while a task is still running", async () => {
    mutateAsync.mockResolvedValueOnce({
      id: "t1",
      status: "running",
      result_ref: null,
      error: null,
      created_at: "2026-09-09T10:00:00Z",
      finished_at: null,
      progress: {},
      type: "tailor",
    });
    const count = renderHook(() => useTailoringCount());

    const { unmount } = renderButton();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /^tailor/i }));
    await screen.findByText("progress:t1");
    expect(count.result.current).toBe(1);

    unmount();
    expect(count.result.current).toBe(0);
  });

  it("defaults to tune mode and sends it in the tailor body when a resume document exists", async () => {
    resumeDocumentData = resumeDocument;
    mutateAsync.mockResolvedValueOnce({
      id: "t1",
      status: "running",
      result_ref: null,
      error: null,
      created_at: "2026-09-09T10:00:00Z",
      finished_at: null,
      progress: {},
      type: "tailor",
    });
    renderButton();
    expect(lightRadio()).toBeChecked();

    const user = userEvent.setup({ delay: null });
    await user.click(screen.getByRole("button", { name: /^tailor/i }));

    expect(mutateAsync).toHaveBeenCalledWith({ jobId: "j1", body: { track_id: null, mode: "tune" } });
  });

  it("sends no mode and resolves no default while the resume document query is in flight", async () => {
    // Guessing "blocks" here would override the API's own "tune when a document exists" default
    // and spend three LLM calls on the wrong mode.
    resumeDocumentData = undefined;
    resumeDocumentPending = true;
    mutateAsync.mockResolvedValueOnce({
      id: "t1",
      status: "running",
      result_ref: null,
      error: null,
      created_at: "2026-09-09T10:00:00Z",
      finished_at: null,
      progress: {},
      type: "tailor",
    });
    renderButton();
    expect(lightRadio()).not.toBeChecked();
    expect(fullRadio()).not.toBeChecked();

    const user = userEvent.setup({ delay: null });
    await user.click(screen.getByRole("button", { name: /^tailor/i }));

    expect(mutateAsync).toHaveBeenCalledWith({ jobId: "j1", body: { track_id: null, mode: null } });
  });

  it("defaults to blocks mode and disables tune mode when there is no resume document", async () => {
    resumeDocumentData = null;
    mutateAsync.mockResolvedValueOnce({
      id: "t1",
      status: "running",
      result_ref: null,
      error: null,
      created_at: "2026-09-09T10:00:00Z",
      finished_at: null,
      progress: {},
      type: "tailor",
    });
    renderButton();
    expect(fullRadio()).toBeChecked();
    expect(lightRadio()).toBeDisabled();
    expect(screen.getByText("To use Light touch, upload your resume file in Your profile.")).toBeInTheDocument();

    const user = userEvent.setup({ delay: null });
    await user.click(screen.getByRole("button", { name: /^tailor/i }));
    expect(mutateAsync).toHaveBeenCalledWith({ jobId: "j1", body: { track_id: null, mode: "blocks" } });
  });

  it("an explicit Full rewrite choice wins over the default", async () => {
    resumeDocumentData = resumeDocument;
    mutateAsync.mockResolvedValueOnce({ id: "t1", status: "running", result_ref: null, error: null, created_at: "x", finished_at: null, progress: {}, type: "tailor" });
    renderButton();
    const user = userEvent.setup({ delay: null });
    await user.click(screen.getByText("Options"));
    await user.click(fullRadio());
    await user.click(screen.getByRole("button", { name: /^tailor/i }));
    expect(mutateAsync).toHaveBeenCalledWith({ jobId: "j1", body: { track_id: null, mode: "blocks" } });
  });
  it("links to Settings instead of offering Tailor when /me reports no AI provider", async () => {
    meData = { user_id: "u1", email: "dev@example.com", llm_configured: false, auth_mode: "token" };
    renderButton();

    expect(screen.getByRole("link", { name: "Add an AI key in Settings" })).toHaveAttribute("href", "/settings");
    expect(screen.queryByRole("button", { name: /^tailor/i })).not.toBeInTheDocument();
    expect(mutateAsync).not.toHaveBeenCalled();
  });

  it("toasts a 409 llm_not_configured from tailor with an Open settings action", async () => {
    mutateAsync.mockRejectedValueOnce(
      new ApiError(409, { title: "Conflict", status: 409, detail: "no AI provider is configured", code: "llm_not_configured" }, "HTTP 409"),
    );
    renderButton();
    const user = userEvent.setup({ delay: null });
    await user.click(screen.getByRole("button", { name: /^tailor/i }));

    expect(toast.error).toHaveBeenCalledWith("no AI provider is configured", {
      action: { label: "Open settings", onClick: expect.any(Function) },
    });
    const options = vi.mocked(toast.error).mock.calls[0]?.[1] as unknown as { action: { onClick: () => void } };
    options.action.onClick();
    expect(push).toHaveBeenCalledWith("/settings");
  });

  it("toasts a 409 llm_key_unreadable from tailor the same way", async () => {
    mutateAsync.mockRejectedValueOnce(
      new ApiError(409, { title: "Conflict", status: 409, detail: "your stored key could not be read", code: "llm_key_unreadable" }, "HTTP 409"),
    );
    renderButton();
    const user = userEvent.setup({ delay: null });
    await user.click(screen.getByRole("button", { name: /^tailor/i }));

    expect(toast.error).toHaveBeenCalledWith("your stored key could not be read", {
      action: { label: "Open settings", onClick: expect.any(Function) },
    });
  });
});
