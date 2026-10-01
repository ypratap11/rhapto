import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SurveyWizard } from "./SurveyWizard";
import { draftKey, loadDraft, saveDraft, SURVEY_STEPS } from "@/lib/feedback";

vi.mock("next/navigation", () => ({ usePathname: () => "/feedback" }));
vi.mock("next/link", () => ({
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

const sameOriginFlag = { value: true };
vi.mock("@/lib/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/client")>();
  return {
    ...actual,
    get SAME_ORIGIN_DEPLOYMENT() {
      return sameOriginFlag.value;
    },
  };
});

const USER = "11111111-1111-4111-8111-111111111111";
const ME = { auth_mode: "access", email: "tester-a@example.com", llm_configured: true, user_id: USER };

type Call = { url: string; method: string; body: unknown };
let calls: Call[];
let feedbackResponse: () => Response;

async function recordedCall(input: RequestInfo | URL, init?: RequestInit): Promise<Call> {
  if (input instanceof Request) {
    const text = await input.clone().text();
    return { url: input.url, method: input.method, body: text ? JSON.parse(text) : undefined };
  }
  return { url: String(input), method: init?.method ?? "GET", body: init?.body ? JSON.parse(String(init.body)) : undefined };
}

const created = () =>
  new Response(JSON.stringify({ id: "22222222-2222-4222-8222-222222222222", created_at: "2026-10-01T00:00:00Z" }), {
    status: 201,
    headers: { "content-type": "application/json" },
  });

beforeEach(() => {
  calls = [];
  feedbackResponse = created;
  window.localStorage.clear();
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const call = await recordedCall(input, init);
      calls.push(call);
      if (call.url.endsWith("/api/v1/me")) {
        return new Response(JSON.stringify(ME), { status: 200, headers: { "content-type": "application/json" } });
      }
      if (call.url.endsWith("/api/v1/feedback")) return feedbackResponse();
      return new Response("{}", { status: 404 });
    }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  window.localStorage.clear();
});

function renderWizard() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SurveyWizard />
    </QueryClientProvider>,
  );
}

const posts = () => calls.filter((c) => c.method === "POST");
const heading = (name: string | RegExp) => screen.findByRole("heading", { level: 2, name });
const STEP_TITLES = SURVEY_STEPS.map((s) => s.title);
const titleOf = (i: number): string => STEP_TITLES[i] ?? "";

async function startWizard() {
  const user = userEvent.setup();
  renderWizard();
  await heading(titleOf(0));
  return user;
}

async function skipTo(user: ReturnType<typeof userEvent.setup>, index: number) {
  for (let i = 0; i < index; i++) await user.click(screen.getByRole("button", { name: "Skip" }));
  await heading(titleOf(index));
}

const NOTICE = /read by the Rhapto maintainer/i;

describe("SurveyWizard navigation", () => {
  it("renders the first of seven steps with progress", async () => {
    await startWizard();
    expect(screen.getByText("Step 1 of 7")).toBeInTheDocument();
    const bar = screen.getByRole("progressbar");
    expect(bar).toHaveAttribute("aria-valuenow", "1");
    expect(bar).toHaveAttribute("aria-valuemax", "7");
    expect(screen.getByRole("button", { name: "Back" })).toBeDisabled();
  });

  it("walks all seven steps by Skip, updating the progress each time", async () => {
    const user = await startWizard();
    for (let i = 1; i < 7; i++) {
      await user.click(screen.getByRole("button", { name: "Skip" }));
      await heading(titleOf(i));
      expect(screen.getByText(`Step ${i + 1} of 7`)).toBeInTheDocument();
      expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", String(i + 1));
    }
    expect(screen.queryByRole("button", { name: "Skip" })).not.toBeInTheDocument(); // last step submits
    expect(screen.getByRole("button", { name: "Submit" })).toBeInTheDocument();
  });

  it("keeps answers across Next, Back and Skip", async () => {
    const user = await startWizard();
    await user.click(screen.getByRole("radio", { name: "Find jobs" }));
    await user.click(screen.getByRole("button", { name: "Next" }));
    await heading(titleOf(1));
    await user.click(screen.getByRole("radio", { name: "4" }));
    await user.type(screen.getByRole("textbox"), "invite was slow");
    await user.click(screen.getByRole("button", { name: "Skip" }));
    await heading(titleOf(2));
    await user.click(screen.getByRole("button", { name: "Back" }));
    await heading(titleOf(1));
    expect(screen.getByRole("radio", { name: "4" })).toBeChecked();
    expect(screen.getByRole("textbox")).toHaveValue("invite was slow");
    await user.click(screen.getByRole("button", { name: "Back" }));
    await heading(titleOf(0));
    expect(screen.getByRole("radio", { name: "Find jobs" })).toBeChecked();
  });

  it("moves focus to the step heading on every step change, and not on first render", async () => {
    const user = await startWizard();
    expect(await heading(titleOf(0))).not.toHaveFocus();
    await user.click(screen.getByRole("button", { name: "Next" }));
    expect(await heading(titleOf(1))).toHaveFocus();
    await user.click(screen.getByRole("button", { name: "Next" }));
    expect(await heading(titleOf(2))).toHaveFocus();
    await user.click(screen.getByRole("button", { name: "Back" }));
    expect(await heading(titleOf(1))).toHaveFocus();
  });

  it("shows the maintainer-reads notice once on step 1 and on none of steps 2 to 7", async () => {
    const user = await startWizard();
    expect(screen.getAllByText(NOTICE)).toHaveLength(1);
    for (let i = 1; i < 7; i++) {
      await user.click(screen.getByRole("button", { name: "Skip" }));
      await heading(titleOf(i));
      expect(screen.queryByText(NOTICE)).not.toBeInTheDocument();
    }
  });

  it("only offers the follow-up text for 'Something else'", async () => {
    const user = await startWizard();
    expect(screen.queryByText("What was it?")).not.toBeInTheDocument();
    await user.click(screen.getByRole("radio", { name: "Something else" }));
    expect(screen.getByText("What was it?")).toBeInTheDocument();
  });

  it("keeps the quote consent unchecked by default", async () => {
    const user = await startWizard();
    await skipTo(user, 6);
    expect(screen.getByRole("checkbox", { name: /quote my answers/i })).not.toBeChecked();
  });
});

describe("SurveyWizard submit", () => {
  it("disables Submit until there is at least one answer", async () => {
    const user = await startWizard();
    await skipTo(user, 6);
    expect(screen.getByRole("button", { name: "Submit" })).toBeDisabled();
    await user.click(screen.getAllByRole("radio", { name: "Maybe" })[0] as HTMLElement);
    expect(screen.getByRole("button", { name: "Submit" })).toBeEnabled();
  });

  it("keeps Submit disabled when the only thing set is the quote consent", async () => {
    const user = await startWizard();
    await skipTo(user, 6);
    await user.click(screen.getByRole("checkbox", { name: /quote my answers/i }));
    expect(screen.getByRole("button", { name: "Submit" })).toBeDisabled();
    await user.click(screen.getAllByRole("radio", { name: "Maybe" })[0] as HTMLElement);
    expect(screen.getByRole("button", { name: "Submit" })).toBeEnabled();
  });

  it("moves focus to the confirmation heading and leaves no draft behind after a send", async () => {
    const user = await startWizard();
    await user.click(screen.getByRole("radio", { name: "Find jobs" }));
    await skipTo(user, 6);
    await user.click(screen.getAllByRole("radio", { name: "Yes" })[0] as HTMLElement);
    await user.click(screen.getByRole("button", { name: "Submit" }));
    expect(await screen.findByRole("heading", { level: 2, name: "Thank you" })).toHaveFocus();
    await act(async () => {
      await new Promise((r) => setTimeout(r, 450));
    });
    expect(window.localStorage.getItem(draftKey(USER))).toBeNull();
  });

  it("posts form survey with only the answered fields, clears the draft and confirms", async () => {
    const user = await startWizard();
    await user.click(screen.getByRole("radio", { name: "Tailor a resume" }));
    await user.click(screen.getByRole("button", { name: "Next" }));
    await heading(titleOf(1));
    await user.click(screen.getByRole("radio", { name: "5" }));
    await user.click(screen.getByRole("button", { name: "Skip" })); // 3
    await user.click(screen.getByRole("button", { name: "Skip" })); // 4
    await user.click(screen.getByRole("button", { name: "Skip" })); // 5
    await user.click(screen.getByRole("button", { name: "Skip" })); // 6
    await user.click(screen.getByRole("button", { name: "Skip" })); // 7
    await user.click(screen.getByRole("checkbox", { name: /quote my answers/i }));
    await user.type(screen.getByRole("textbox", { name: /fix first/i }), "Import speed");
    await user.click(screen.getByRole("button", { name: "Submit" }));

    expect(await screen.findByText(/your answers were sent/i)).toBeInTheDocument();
    expect(posts()).toHaveLength(1);
    expect(posts()[0]?.url).toMatch(/\/api\/v1\/feedback$/);
    expect(posts()[0]?.body).toEqual({
      form: "survey",
      answers: {
        session: { task: "tailor_resume" },
        getting_started: { ease: 5 },
        overall: { fix_first: "Import speed", quote_ok: true },
      },
    });
    expect(window.localStorage.getItem(draftKey(USER))).toBeNull();
    expect(screen.getByRole("link", { name: "Back to dashboard" })).toHaveAttribute("href", "/dashboard");
  });

  it("starts empty on a re-visit and stores a second response when submitted again (AC 2)", async () => {
    const first = renderWizard();
    const user = userEvent.setup();
    await heading(titleOf(0));
    await user.click(screen.getByRole("radio", { name: "Find jobs" }));
    await skipTo(user, 6);
    await user.click(screen.getAllByRole("radio", { name: "Yes" })[0] as HTMLElement);
    await user.click(screen.getByRole("button", { name: "Submit" }));
    await screen.findByText(/your answers were sent/i);
    first.unmount();

    renderWizard();
    await heading(titleOf(0));
    expect(screen.queryByText(/restored your unsent answers/i)).not.toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "Find jobs" })).not.toBeChecked();
    await user.click(screen.getByRole("radio", { name: "Set up my profile" }));
    await skipTo(user, 6);
    await user.click(screen.getAllByRole("radio", { name: "No" })[0] as HTMLElement);
    await user.click(screen.getByRole("button", { name: "Submit" }));
    await screen.findByText(/your answers were sent/i);
    expect(posts()).toHaveLength(2);
  });

  it("keeps the answers and the draft, with an inline message, when the server refuses", async () => {
    feedbackResponse = () =>
      new Response(JSON.stringify({ type: "about:blank", title: "Too many", status: 429, detail: "Slow down a little." }), {
        status: 429,
        headers: { "content-type": "application/problem+json" },
      });
    const user = await startWizard();
    await user.click(screen.getByRole("radio", { name: "Find jobs" }));
    await skipTo(user, 6);
    await user.type(screen.getByRole("textbox", { name: /fix first/i }), "keep me");
    await user.click(screen.getByRole("button", { name: "Submit" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Slow down a little.");
    expect(screen.queryByText(/your answers were sent/i)).not.toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: /fix first/i })).toHaveValue("keep me");
    await waitFor(() => expect(loadDraft(USER)?.answers.overall?.fix_first).toBe("keep me"), { timeout: 2000 });
  });
});

describe("SurveyWizard draft", () => {
  it("saves a draft about 300 ms after the last change, under the per-user key", async () => {
    const user = await startWizard();
    await user.click(screen.getByRole("radio", { name: "Find jobs" }));
    expect(window.localStorage.getItem(draftKey(USER))).toBeNull(); // debounced, not immediate
    await waitFor(() => expect(loadDraft(USER)?.answers.session?.task).toBe("find_jobs"), { timeout: 2000 });
  });

  it("restores an unsent draft, says so, and 'Start over' clears it", async () => {
    saveDraft(USER, { savedAt: Date.now(), step: 1, answers: { getting_started: { ease: 2, stuck: "the token step" } } });
    const user = userEvent.setup();
    renderWizard();
    await heading(titleOf(1));
    expect(screen.getByText(/restored your unsent answers/i)).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "2" })).toBeChecked();
    expect(screen.getByRole("textbox")).toHaveValue("the token step");

    await user.click(screen.getByRole("button", { name: "Start over" }));
    await heading(titleOf(0));
    expect(screen.queryByText(/restored your unsent answers/i)).not.toBeInTheDocument();
    expect(window.localStorage.getItem(draftKey(USER))).toBeNull();
    await user.click(screen.getByRole("button", { name: "Next" }));
    await heading(titleOf(1));
    expect(screen.getByRole("radio", { name: "2" })).not.toBeChecked();
    // and the emptied form does not write itself back
    await act(async () => {
      await new Promise((r) => setTimeout(r, 450));
    });
    expect(window.localStorage.getItem(draftKey(USER))).toBeNull();
  });

  it("works with storage blocked: no draft, no crash, still submits", async () => {
    // Only the draft key is blocked: the API client reads its own connection settings from storage
    // and is out of scope here; what is under test is that the draft feature goes inert.
    const real = {
      getItem: Storage.prototype.getItem,
      setItem: Storage.prototype.setItem,
      removeItem: Storage.prototype.removeItem,
    };
    const blocked = (key: string) => key.startsWith("rhapto.feedback.draft");
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(function (this: Storage, key: string) {
      if (blocked(key)) throw new Error("blocked");
      return real.getItem.call(this, key);
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(function (this: Storage, key: string, value: string) {
      if (blocked(key)) throw new Error("blocked");
      real.setItem.call(this, key, value);
    });
    vi.spyOn(Storage.prototype, "removeItem").mockImplementation(function (this: Storage, key: string) {
      if (blocked(key)) throw new Error("blocked");
      real.removeItem.call(this, key);
    });
    const user = await startWizard();
    await user.click(screen.getByRole("radio", { name: "Find jobs" }));
    await skipTo(user, 6);
    await user.click(screen.getAllByRole("radio", { name: "Maybe" })[0] as HTMLElement);
    await user.click(screen.getByRole("button", { name: "Submit" }));
    expect(await screen.findByText(/your answers were sent/i)).toBeInTheDocument();
  });
});

describe("SurveyWizard keyboard", () => {
  async function tabTo(user: ReturnType<typeof userEvent.setup>, name: string) {
    for (let i = 0; i < 40; i++) {
      await user.tab();
      const el = document.activeElement;
      if (el && el.tagName === "BUTTON" && el.textContent?.trim() === name) return;
    }
    throw new Error(`never reached the "${name}" button by Tab`);
  }

  it("completes and submits using only the keyboard", async () => {
    const user = await startWizard();
    // Step 1: Tab onto the first radio of the first group, choose it with Space.
    await user.keyboard("{Tab}");
    expect(screen.getByRole("radio", { name: "Find jobs" })).toHaveFocus();
    await user.keyboard(" ");
    expect(screen.getByRole("radio", { name: "Find jobs" })).toBeChecked();
    await tabTo(user, "Next");
    await user.keyboard("{Enter}");

    // Step 2: focus is on the heading; Tab to the rating group, arrow to 2.
    expect(await heading(titleOf(1))).toHaveFocus();
    await user.keyboard("{Tab}");
    expect(screen.getByRole("radio", { name: "1" })).toHaveFocus();
    await user.keyboard("{ArrowRight}");
    expect(screen.getByRole("radio", { name: "2" })).toBeChecked();
    await tabTo(user, "Next");
    await user.keyboard("{Enter}");

    for (let i = 2; i < 6; i++) {
      await heading(titleOf(i));
      await tabTo(user, "Skip");
      await user.keyboard("{Enter}");
    }
    await heading(titleOf(6));
    await tabTo(user, "Submit");
    await user.keyboard("{Enter}");

    expect(await screen.findByText(/your answers were sent/i)).toBeInTheDocument();
    expect(posts()[0]?.body).toEqual({
      form: "survey",
      answers: { session: { task: "find_jobs" }, getting_started: { ease: 2 } },
    });
  });
});
