import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { PackageOut } from "@/lib/api/queries";
import * as copy from "@/lib/coach/copy";
import { ResultStep } from "./ResultStep";

const pkg: { current: Partial<PackageOut> } = { current: {} };
const fire = vi.fn<(step: string) => Promise<void>>(async () => undefined);
const download = vi.fn<(...args: unknown[]) => Promise<void>>(async () => undefined);
vi.mock("@/lib/coach/events", () => ({ fireCoachEvent: (step: string) => fire(step) }));
vi.mock("@/lib/download", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/download")>()),
  downloadAuthenticated: (...args: unknown[]) => download(...args),
}));
vi.mock("@/lib/api/queries", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/queries")>()),
  usePackage: () => ({ data: pkg.current, isLoading: false, error: null }),
  useAnswers: () => ({ data: { name: "Maya Chen" }, isLoading: false }),
}));

const ready = {
  id: "pk1", job_id: "j1", status: "draft", mode: "tune", has_docx: true, has_pdf: true,
  edits: [
    { paragraph_id: "p9", before: "Led the Snowflake migration for 12 teams, cutting warehouse cost 30%.", after: "Led the Snowflake migration for 12 teams, reducing warehouse cost 30%.", reason: "mirrors the JD's wording" },
  ],
} as unknown as PackageOut;
const blocked = { ...ready, status: "blocked", has_docx: false, has_pdf: false } as unknown as PackageOut;

const mount = (over: Partial<React.ComponentProps<typeof ResultStep>> = {}) =>
  render(<ResultStep packageId="pk1" error={null} retryBusy={false} onRetry={vi.fn()} onAnother={vi.fn()} {...over} />);

beforeEach(() => { fire.mockClear(); download.mockClear(); pkg.current = ready; });

describe("ResultStep", () => {
  it("ready: plain status, both downloads, what changed, and a link to the full details", async () => {
    mount();
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Your tailored resume");
    expect(screen.getByText(/ready for you to read/i)).toBeInTheDocument();
    expect(screen.getByText("mirrors the JD's wording")).toBeInTheDocument();
    expect(screen.getByText(/reducing warehouse cost 30%/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /see full details/i })).toHaveAttribute("href", "/jobs/j1/packages/pk1");
    expect(document.body.textContent).not.toMatch(/guardrail|llm|tokens|track /i);
    await userEvent.setup({ delay: null }).click(screen.getByRole("button", { name: /download docx/i }));
    await waitFor(() => expect(fire).toHaveBeenCalledWith("downloaded"));
    expect(download).toHaveBeenCalledWith("/api/v1/packages/pk1/files/resume.docx", "Maya_Chen_Resume.docx");
  });

  it("ready: shows the shared coach copy", () => {
    mount();
    expect(screen.getByRole("heading", { level: 1, name: copy.RESULT_TITLE })).toBeInTheDocument();
    expect(screen.getByText(copy.RESULT_READY)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: copy.DOWNLOAD_DOCX })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: copy.DOWNLOAD_PDF })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: copy.WHAT_CHANGED })).toBeInTheDocument();
  });

  it("a failed download fires no event and says so in plain words", async () => {
    download.mockRejectedValueOnce(new Error("boom"));
    mount();
    await userEvent.setup({ delay: null }).click(screen.getByRole("button", { name: /download docx/i }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(fire).not.toHaveBeenCalled();
  });

  it("only offers the PDF when one exists", () => {
    pkg.current = { ...ready, has_pdf: false } as unknown as PackageOut;
    mount();
    expect(screen.queryByRole("button", { name: /download pdf/i })).toBeNull();
  });

  it("'Try another' goes back to the matches", async () => {
    const onAnother = vi.fn();
    mount({ onAnother });
    await userEvent.setup({ delay: null }).click(screen.getByRole("button", { name: /try another/i }));
    expect(onAnother).toHaveBeenCalled();
  });

  it("blocked_package_offers_no_download_and_a_retry_that_says_it_costs_a_run", async () => {
    pkg.current = blocked;
    const onRetry = vi.fn();
    const onAnother = vi.fn();
    mount({ onRetry, onAnother });
    expect(screen.getByText("Rhapto stopped this draft because it added something that isn't in your resume")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /download/i })).toBeNull();
    const retry = screen.getByRole("button", { name: /try again.*another run/i });
    const user = userEvent.setup({ delay: null });
    await user.click(retry);
    expect(onRetry).toHaveBeenCalledWith(blocked);
    await user.click(screen.getByRole("button", { name: /pick another job/i }));
    expect(onAnother).toHaveBeenCalled();
  });

  it("blocked_package_names_the_rule_that_fired_in_plain_words", () => {
    pkg.current = {
      ...blocked,
      guardrail_report: {
        passed: false,
        rules_run: ["tune-scope", "no-new-numbers"],
        violations: [
          { rule: "no-new-numbers", severity: "error", path: "edits[0]", message: "number(s) not found in the document: 45" },
          { rule: "tune-scope", severity: "warning", path: "edits[1]", message: "a warning that did not block" },
        ],
      },
    } as unknown as PackageOut;
    mount();
    const fired = screen.getByRole("list", { name: /what stopped it/i });
    expect(fired).toHaveTextContent("no-new-numbers");
    expect(fired).toHaveTextContent("A number that isn't in your resume");
    expect(fired).toHaveTextContent("number(s) not found in the document: 45");
    expect(fired).not.toHaveTextContent("tune-scope"); // a warning did not stop the draft
  });

  const blockedBy = (...rules: string[]) =>
    ({
      ...blocked,
      guardrail_report: {
        passed: false,
        rules_run: rules,
        violations: rules.map((rule, i) => ({ rule, severity: "error", path: `edits[${i}]`, message: `${rule} said no` })),
      },
    }) as unknown as PackageOut;

  it("blocked_by_invented_content_says_it_added_something_not_in_the_resume", () => {
    pkg.current = blockedBy("no-new-numbers", "no-invented-entities");
    mount();
    expect(screen.getByText("Rhapto stopped this draft because it added something that isn't in your resume")).toBeInTheDocument();
    expect(screen.queryByText(/didn't pass one of its checks/)).toBeNull();
  });

  it("blocked_by_any_other_rule_says_it_failed_a_check_and_still_names_the_rule", () => {
    pkg.current = blockedBy("no-new-numbers", "date-consistency");
    mount();
    expect(screen.getByText("Rhapto stopped this draft because it didn't pass one of its checks")).toBeInTheDocument();
    expect(screen.queryByText(/added something that isn't in your resume/)).toBeNull();
    const fired = screen.getByRole("list", { name: /what stopped it/i });
    expect(fired).toHaveTextContent("date-consistency");
    expect(fired).toHaveTextContent("Dates that don't line up with your resume");
  });

  it("the retry is disabled while a retry is starting", () => {
    pkg.current = blocked;
    mount({ retryBusy: true });
    expect(screen.getByRole("button", { name: /try again/i })).toBeDisabled();
  });

  it("blocked: a refused retry is shown next to the button, with the Settings way forward", () => {
    pkg.current = blocked;
    mount({ error: { message: "You have used all 3 free tailoring runs on this instance. Add your own provider API key in Settings to keep going.", next: "settings", link: { label: "Open Settings", href: "/settings" } } });
    expect(screen.getByRole("alert")).toHaveTextContent("You have used all 3 free tailoring runs");
    expect(screen.getByRole("link", { name: "Open Settings" })).toHaveAttribute("href", "/settings");
    expect(screen.getByRole("button", { name: /try again \(uses another run\)/i })).toBeInTheDocument();
  });
});
