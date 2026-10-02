import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { FeedbackButton } from "./FeedbackButton";
import { setSettings } from "@/lib/api/client";

const pathname = { current: "/dashboard" };
vi.mock("next/navigation", () => ({ usePathname: () => pathname.current }));

const sameOriginFlag = { value: false };
vi.mock("@/lib/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/client")>();
  return {
    ...actual,
    get SAME_ORIGIN_DEPLOYMENT() {
      return sameOriginFlag.value;
    },
  };
});

const toastSuccess = vi.fn();
vi.mock("sonner", () => ({ toast: { success: (...a: unknown[]) => toastSuccess(...a), error: vi.fn() } }));

const JOB = "0b9f6c1e-3a4d-4e5f-8a7b-1c2d3e4f5a6b";
const PKG = "9a8b7c6d-5e4f-4a3b-8c2d-1e0f9a8b7c6d";
const ME = { auth_mode: "access", email: "tester-a@example.com", llm_configured: true, user_id: "11111111-1111-4111-8111-111111111111" };

type Call = { url: string; method: string; body: unknown };
let calls: Call[];
let meStatus = 200;
let feedbackResponse: () => Response;

async function recordedCall(input: RequestInfo | URL, init?: RequestInit): Promise<Call> {
  if (input instanceof Request) {
    const text = await input.clone().text();
    return { url: input.url, method: input.method, body: text ? JSON.parse(text) : undefined };
  }
  return { url: String(input), method: init?.method ?? "GET", body: init?.body ? JSON.parse(String(init.body)) : undefined };
}

beforeEach(() => {
  calls = [];
  meStatus = 200;
  feedbackResponse = () =>
    new Response(JSON.stringify({ id: "22222222-2222-4222-8222-222222222222", created_at: "2026-10-01T00:00:00Z" }), {
      status: 201,
      headers: { "content-type": "application/json" },
    });
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const call = await recordedCall(input, init);
      calls.push(call);
      if (call.url.endsWith("/api/v1/me")) {
        return new Response(JSON.stringify(meStatus === 200 ? ME : { type: "about:blank", title: "boom", status: meStatus }), {
          status: meStatus,
          headers: { "content-type": meStatus === 200 ? "application/json" : "application/problem+json" },
        });
      }
      if (call.url.endsWith("/api/v1/feedback")) return feedbackResponse();
      return new Response("{}", { status: 404 });
    }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
  window.localStorage.clear();
  sameOriginFlag.value = false;
  toastSuccess.mockClear();
});

function renderButton() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <FeedbackButton />
    </QueryClientProvider>,
  );
}

/** Let every query that is going to fire actually fire and resolve, so "no call" is not vacuous. */
async function settle() {
  await act(async () => {
    await new Promise((r) => setTimeout(r, 50));
  });
}

const meCalls = () => calls.filter((c) => c.url.endsWith("/api/v1/me"));
const BUTTON = { name: "Feedback on this page" };

describe("FeedbackButton /me discipline (condition 4)", () => {
  it("makes no /me call on / in access mode -- and the same harness does make one on /dashboard", async () => {
    sameOriginFlag.value = true;
    pathname.current = "/";
    const first = renderButton();
    await settle();
    expect(meCalls()).toHaveLength(0);
    expect(screen.queryByRole("button", BUTTON)).not.toBeInTheDocument();
    first.unmount();

    // Positive control: identical harness, app route. If this fails, the assertion above proves nothing.
    pathname.current = "/dashboard";
    renderButton();
    expect(await screen.findByRole("button", BUTTON)).toBeInTheDocument();
    expect(meCalls().length).toBeGreaterThan(0);
  });

  it("makes no /me call on / in token mode with a token stored -- and does on /dashboard", async () => {
    setSettings({ token: "tok", apiUrl: "http://localhost:8000" });
    pathname.current = "/";
    const first = renderButton();
    await settle();
    expect(meCalls()).toHaveLength(0);
    first.unmount();

    pathname.current = "/dashboard";
    renderButton();
    expect(await screen.findByRole("button", BUTTON)).toBeInTheDocument();
    expect(meCalls().length).toBeGreaterThan(0);
  });

  it("makes no /me call in token mode with no token", async () => {
    pathname.current = "/dashboard";
    renderButton();
    await settle();
    expect(meCalls()).toHaveLength(0);
    expect(screen.queryByRole("button", BUTTON)).not.toBeInTheDocument();
  });
});

describe("FeedbackButton visibility", () => {
  beforeEach(() => {
    sameOriginFlag.value = true;
  });

  it.each(["/about", "/feedback"])("is hidden on %s", async (path) => {
    pathname.current = path;
    renderButton();
    await settle();
    expect(screen.queryByRole("button", BUTTON)).not.toBeInTheDocument();
  });

  it("is hidden when /me errors", async () => {
    meStatus = 500;
    pathname.current = "/dashboard";
    renderButton();
    await settle();
    expect(meCalls().length).toBeGreaterThan(0); // it did ask; it just did not get a user
    expect(screen.queryByRole("button", BUTTON)).not.toBeInTheDocument();
  });

  it("is shown on /dashboard", async () => {
    pathname.current = "/dashboard";
    renderButton();
    expect(await screen.findByRole("button", BUTTON)).toBeInTheDocument();
  });
});

describe("QuickFeedbackDialog", () => {
  beforeEach(() => {
    sameOriginFlag.value = true;
  });

  async function openDialog() {
    const user = userEvent.setup();
    renderButton();
    await user.click(await screen.findByRole("button", BUTTON));
    return user;
  }

  it("posts a quick form with the review area and both ids on a review page, then closes and toasts", async () => {
    pathname.current = `/jobs/${JOB}/packages/${PKG}`;
    const user = await openDialog();
    await user.click(screen.getByRole("radio", { name: /confusing/i }));
    await user.click(screen.getByRole("radio", { name: "4" }));
    await user.type(screen.getByRole("textbox"), "The flagged line was unclear.");
    await user.click(screen.getByRole("button", { name: /send/i }));

    await waitFor(() => expect(toastSuccess).toHaveBeenCalled());
    const post = calls.find((c) => c.method === "POST");
    expect(post?.url).toMatch(/\/api\/v1\/feedback$/);
    expect(post?.body).toEqual({
      form: "quick",
      page_area: "review",
      job_id: JOB,
      package_id: PKG,
      answers: { kind: "confusing", rating: 4, text: "The flagged line was unclear." },
    });
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("omits ids and optional answers where there are none", async () => {
    pathname.current = "/dashboard";
    const user = await openDialog();
    await user.click(screen.getByRole("radio", { name: /it worked well/i }));
    await user.click(screen.getByRole("button", { name: /send/i }));
    await waitFor(() => expect(toastSuccess).toHaveBeenCalled());
    expect(calls.find((c) => c.method === "POST")?.body).toEqual({
      form: "quick",
      page_area: "dashboard",
      answers: { kind: "worked_well" },
    });
  });

  it("keeps the dialog and the typed text, with an inline message, when the server refuses", async () => {
    feedbackResponse = () =>
      new Response(JSON.stringify({ type: "about:blank", title: "Too many", status: 429, detail: "Slow down a little." }), {
        status: 429,
        headers: { "content-type": "application/problem+json" },
      });
    pathname.current = "/dashboard";
    const user = await openDialog();
    await user.click(screen.getByRole("radio", { name: /bug/i }));
    await user.type(screen.getByRole("textbox"), "keep me");
    await user.click(screen.getByRole("button", { name: /send/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Slow down a little.");
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByRole("textbox")).toHaveValue("keep me");
    expect(toastSuccess).not.toHaveBeenCalled();
  });

  it("limits the text to 2000 characters and shows a counter", async () => {
    pathname.current = "/dashboard";
    const user = await openDialog();
    const box = screen.getByRole("textbox");
    expect(box).toHaveAttribute("maxlength", "2000");
    expect(screen.getByText("0 / 2000")).toBeInTheDocument();
    await user.type(box, "abc");
    expect(screen.getByText("3 / 2000")).toBeInTheDocument();
  });

  it("states once that the maintainer reads the answers, and links to the full survey", async () => {
    pathname.current = "/dashboard";
    await openDialog();
    expect(screen.getAllByText(/read by the Rhapto maintainer/i)).toHaveLength(1);
    expect(screen.getByRole("link", { name: /take the full survey/i })).toHaveAttribute("href", "/feedback");
  });

  it("does not send until a kind is chosen", async () => {
    pathname.current = "/dashboard";
    await openDialog();
    expect(screen.getByRole("button", { name: /send/i })).toBeDisabled();
  });
});
