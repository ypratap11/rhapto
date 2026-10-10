import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ACCESS_REQUEST_MAILTO, ACCESS_REQUEST_URL } from "./access";
import { Landing } from "./Landing";

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

beforeEach(() => vi.stubEnv("NEXT_PUBLIC_TRIAL_RUNS", "5"));

afterEach(() => {
  vi.unstubAllEnvs();
  sameOriginFlag.value = true;
});

describe("Landing, the light front door", () => {
  it("has exactly a hero, a tour, three steps and one proof", () => {
    const { container } = render(<Landing />);
    expect(screen.getAllByTestId("hero-band")).toHaveLength(1);
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(container.querySelectorAll("section")).toHaveLength(3); // tour + steps + proof; the hero is a band
    const steps = within(screen.getByRole("list", { name: /three steps/i })).getAllByRole("listitem");
    expect(steps.map((li) => li.textContent)).toEqual([
      expect.stringContaining("Upload your resume"),
      expect.stringContaining("Pick a job"),
      expect.stringContaining("Download your tailored resume"),
    ]);
    expect(screen.getByText("no-new-numbers")).toBeInTheDocument();
  });

  it("hosted: Tailor my resume goes to /start; Request beta access is a secondary text link; no Sign in", () => {
    render(<Landing />);
    const hero = screen.getAllByTestId("hero-band")[0]!;
    const cta = within(hero).getByRole("link", { name: "Tailor my resume" });
    expect(cta).toHaveAttribute("href", "/start");
    expect(cta.className).toMatch(/bg-primary/);
    expect(cta.className).toContain("shadow-cta");
    expect(within(hero).getByRole("link", { name: /Tailor my resume/ }).textContent).toContain("→");
    const requests = within(hero).getAllByRole("link", { name: "Request beta access" });
    expect(requests).toHaveLength(2);
    const request = requests[0]!;
    // The request link is the owner's form (external, new tab) while ACCESS_REQUEST_URL is set, else the mailto.
    expect(request).toHaveAttribute("href", ACCESS_REQUEST_URL || ACCESS_REQUEST_MAILTO);
    if (ACCESS_REQUEST_URL) expect(request).toHaveAttribute("target", "_blank");
    expect(request.className).not.toMatch(/bg-primary/);
    expect(screen.queryByRole("link", { name: /sign in/i })).toBeNull();
    // The hero line plus the tour line: pins the two-places rule.
    expect(screen.getAllByText("No invite yet?", { exact: false })).toHaveLength(2);
    expect(within(hero).getByText(/first resume import and 5 AI runs are on us/)).toBeInTheDocument(); // NEXT_PUBLIC_TRIAL_RUNS=5 via vi.stubEnv
  });

  it("hosted: the secondary link jumps to the tour on the page", () => {
    render(<Landing />);
    expect(screen.getByRole("link", { name: /See how it works/ })).toHaveAttribute("href", "#tour");
  });

  it("token mode keeps its own hero: Get started -> /settings, no request link, see-how jumps to #tour", () => {
    sameOriginFlag.value = false;
    render(<Landing />);
    expect(screen.getByRole("link", { name: "Get started" })).toHaveAttribute("href", "/settings");
    expect(screen.getByRole("link", { name: /See how it works/ })).toHaveAttribute("href", "#tour");
    expect(document.querySelector("a[href='/start']")).toBeNull();
    expect(screen.queryByRole("link", { name: /request beta access|tailor my resume/i })).toBeNull();
    expect(screen.getByText(/Free and open source \(AGPL-3\.0\)/)).toBeInTheDocument();
  });

  it("does not link to /about and does not contain the moved detail", () => {
    const { container } = render(<Landing />);
    expect(container.querySelector("a[href='/about']")).toBeNull();
    expect(screen.queryByRole("link", { name: /how it works in detail/i })).toBeNull();
    for (const moved of [/Why this exists/, /Why not just ask a chatbot/, /For developers/, /Before you start/, /What it costs/]) {
      expect(screen.queryByText(moved)).toBeNull();
    }
    expect(container.querySelector("#how, #honest, #developers")).toBeNull();
    expect(container.querySelectorAll("#tour")).toHaveLength(1);
    expect(container.textContent).not.toMatch(/provenance|no-unverified-metrics/);
  });

  it("hero copy: badge, subline, facts strip, free-limit line", () => {
    render(<Landing />);
    expect(screen.getByText(/first resume import and 5 AI runs are on us/)).toBeInTheDocument(); // NEXT_PUBLIC_TRIAL_RUNS=5 via vi.stubEnv
    expect(screen.getByText("Every number checked against your resume")).toBeInTheDocument();
    expect(screen.getByText("Upload your resume, pick a job, and get your own document rewritten for it.")).toBeInTheDocument();
    expect(screen.getByText("Open source · You always submit · Your own document")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1 }).className).toContain("font-semibold");
    expect(screen.getByText("defend").tagName).toBe("SPAN");
    expect(screen.getByText("defend").className).toContain("highlight-underline");
  });

  it("numbered step circles carry the three step colours", () => {
    render(<Landing />);
    const circles = within(screen.getByRole("list", { name: /three steps/i })).getAllByText(/^[123]$/);
    expect(circles.map((c) => c.className)).toEqual([
      expect.stringContaining("bg-step-1 text-step-1-fg"),
      expect.stringContaining("bg-step-2 text-step-2-fg"),
      expect.stringContaining("bg-step-3 text-step-3-fg"),
    ]);
  });

  it("keeps the client boundary in the children, not in Landing", () => {
    const dir = dirname(fileURLToPath(import.meta.url));
    const code = readFileSync(join(dir, "Landing.tsx"), "utf8")
      .replace(/\/\*[\s\S]*?\*\//g, "")
      .replace(/^[ \t]*\/\/.*$/gm, "");
    expect(code).not.toMatch(/["']use client["']/);
    expect(code).not.toMatch(/\buse(State|Effect|Ref|Memo|Callback|Reducer)\b/);
  });
});

const CLAIM = /\b(the\s+)?(only|first)\s+(tool|app|product|copilot|resume\s+(tool|builder)|one)\b/i;

describe("marketing claims (I4)", () => {
  it("the regex catches a real claim and spares the retained honest lines", () => {
    expect(CLAIM.test("The only resume tool that checks numbers")).toBe(true);
    expect(CLAIM.test("the first copilot of its kind")).toBe(true);
    expect(CLAIM.test("Free during the beta: your first resume import and 5 AI runs are on us")).toBe(false);
    expect(CLAIM.test("The AI's first draft said")).toBe(false);
  });
  it.each([true, false])("rendered text has no only/first claim (hosted=%s)", (hosted) => {
    sameOriginFlag.value = hosted;
    const { container } = render(<Landing />);
    expect(container.textContent).not.toMatch(CLAIM);
  });
});
