import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { FeedbackButton } from "./FeedbackButton";
import { SurveyWizard } from "./SurveyWizard";
import { SURVEY_STEPS } from "@/lib/feedback";

// QA: every way the server can refuse or fail, and the tester's typed words must survive each one.

vi.mock("next/navigation", () => ({ usePathname: () => "/dashboard" }));
vi.mock("next/link", () => ({
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));
vi.mock("@/lib/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/client")>();
  return {
    ...actual,
    get SAME_ORIGIN_DEPLOYMENT() {
      return true;
    },
  };
});
const toastSuccess = vi.fn();
vi.mock("sonner", () => ({ toast: { success: (...a: unknown[]) => toastSuccess(...a), error: vi.fn() } }));

const ME = {
  auth_mode: "access",
  email: "tester-a@example.com",
  llm_configured: true,
  user_id: "11111111-1111-4111-8111-111111111111",
};
const OK = () =>
  new Response(JSON.stringify({ id: "22222222-2222-4222-8222-222222222222", created_at: "2026-10-01T00:00:00Z" }), {
    status: 201,
    headers: { "content-type": "application/json" },
  });
const problem = (status: number, extra: Record<string, unknown> = {}) =>
  new Response(JSON.stringify({ type: "about:blank", title: `Status ${status}`, status, ...extra }), {
    status,
    headers: { "content-type": "application/problem+json" },
  });

let feedbackResponse: () => Response | Promise<Response>;
let posts: number;

beforeEach(() => {
  posts = 0;
  feedbackResponse = OK;
  window.localStorage.clear();
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = input instanceof Request ? input.url : String(input);
      if (url.endsWith("/api/v1/me")) {
        return new Response(JSON.stringify(ME), { status: 200, headers: { "content-type": "application/json" } });
      }
      if (url.endsWith("/api/v1/feedback")) {
        posts += 1;
        return feedbackResponse();
      }
      return new Response("{}", { status: 404 });
    }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
  window.localStorage.clear();
  toastSuccess.mockClear();
});

function wrap(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

async function openQuick() {
  const user = userEvent.setup();
  wrap(<FeedbackButton />);
  await user.click(await screen.findByRole("button", { name: "Feedback on this page" }));
  await user.click(screen.getByRole("radio", { name: /bug/i }));
  await user.type(screen.getByRole("textbox"), "Words I do not want to lose \u{1F600} שלום");
  return user;
}

const FAILURES: Array<[string, () => Response | Promise<Response>]> = [
  ["422 with field errors", () => problem(422, { errors: [{ loc: ["body", "answers", "text"], msg: "too long" }] })],
  ["429", () => problem(429, { detail: "too much feedback; try later" })],
  ["500 problem+json", () => problem(500)],
  ["500 HTML error page", () => new Response("<html><body>Bad gateway</body></html>", { status: 502, headers: { "content-type": "text/html" } })],
  ["network failure", () => Promise.reject(new TypeError("Failed to fetch"))],
];

describe("quick dialog failures", () => {
  it.each(FAILURES)("keeps the dialog and the typed text after a %s, with a plain message", async (_name, make) => {
    feedbackResponse = make;
    const user = await openQuick();
    await user.click(screen.getByRole("button", { name: /send/i }));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent?.trim().length).toBeGreaterThan(0);
    expect(alert.textContent).not.toMatch(/at \w+\.|stack|TypeError|<html|undefined|\[object/i);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByRole("textbox")).toHaveValue("Words I do not want to lose \u{1F600} שלום");
    expect(screen.getByRole("radio", { name: /bug/i })).toBeChecked();
    expect(toastSuccess).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: /send/i })).toBeEnabled();
  });

  it("lets the tester retry after a failure and then succeeds exactly once more", async () => {
    feedbackResponse = () => problem(500);
    const user = await openQuick();
    await user.click(screen.getByRole("button", { name: /send/i }));
    await screen.findByRole("alert");
    feedbackResponse = OK;
    await user.click(screen.getByRole("button", { name: /send/i }));
    await waitFor(() => expect(toastSuccess).toHaveBeenCalledTimes(1));
    expect(posts).toBe(2);
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("clears the previous error message when the next attempt starts", async () => {
    feedbackResponse = () => problem(500);
    const user = await openQuick();
    await user.click(screen.getByRole("button", { name: /send/i }));
    await screen.findByRole("alert");
    let release: (r: Response) => void = () => {};
    feedbackResponse = () => new Promise<Response>((resolve) => (release = resolve));
    await user.click(screen.getByRole("button", { name: /send/i }));
    await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
    expect(screen.getByRole("button", { name: /sending/i })).toBeDisabled();
    release(OK());
    await waitFor(() => expect(toastSuccess).toHaveBeenCalled());
  });

  it("does not double-post when Send is clicked twice while the first request is in flight", async () => {
    let release: (r: Response) => void = () => {};
    feedbackResponse = () => new Promise<Response>((resolve) => (release = resolve));
    const user = await openQuick();
    await user.click(screen.getByRole("button", { name: /send/i }));
    await user.click(screen.getByRole("button", { name: /sending/i }));
    release(OK());
    await waitFor(() => expect(toastSuccess).toHaveBeenCalledTimes(1));
    expect(posts).toBe(1);
  });
});

describe("survey failures", () => {
  const titleOf = (i: number): string => SURVEY_STEPS[i]?.title ?? "";

  it.each(FAILURES)("keeps every answer after a %s", async (_name, make) => {
    feedbackResponse = make;
    const user = userEvent.setup();
    wrap(<SurveyWizard />);
    await screen.findByRole("heading", { level: 2, name: titleOf(0) });
    await user.click(screen.getByRole("radio", { name: "Find jobs" }));
    for (let i = 0; i < 6; i++) await user.click(screen.getByRole("button", { name: "Skip" }));
    await screen.findByRole("heading", { level: 2, name: titleOf(6) });
    await user.type(screen.getByRole("textbox", { name: /fix first/i }), "line one\nline two \u{1F680}");
    await user.click(screen.getByRole("button", { name: "Submit" }));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).not.toMatch(/<html|TypeError|undefined|\[object/i);
    expect(screen.queryByText(/your answers were sent/i)).not.toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: /fix first/i })).toHaveValue("line one\nline two \u{1F680}");
    expect(screen.getByRole("button", { name: "Submit" })).toBeEnabled();
  });

  it("survives a localStorage accessor that throws (blocked site data)", async () => {
    vi.spyOn(window, "localStorage", "get").mockImplementation(() => {
      throw new DOMException("denied", "SecurityError");
    });
    const user = userEvent.setup();
    wrap(<SurveyWizard />);
    await screen.findByRole("heading", { level: 2, name: titleOf(0) });
    await user.click(screen.getByRole("radio", { name: "Find jobs" }));
    await user.click(screen.getByRole("button", { name: "Next" }));
    await screen.findByRole("heading", { level: 2, name: titleOf(1) });
    vi.restoreAllMocks();
  });
});
