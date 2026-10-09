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
  it("has exactly a hero, three steps and one proof", () => {
    const { container } = render(<Landing />);
    expect(screen.getAllByTestId("hero-band")).toHaveLength(1);
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(container.querySelectorAll("section")).toHaveLength(2); // steps + proof; the hero is a band
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
    const request = within(hero).getByRole("link", { name: "Request beta access" });
    // The request link is the owner's form (external, new tab) while ACCESS_REQUEST_URL is set, else the mailto.
    expect(request).toHaveAttribute("href", ACCESS_REQUEST_URL || ACCESS_REQUEST_MAILTO);
    if (ACCESS_REQUEST_URL) expect(request).toHaveAttribute("target", "_blank");
    expect(request.className).not.toMatch(/bg-primary/);
    expect(screen.queryByRole("link", { name: /sign in/i })).toBeNull();
    expect(within(hero).getByText(/first resume import and 5 AI runs are on us/)).toBeInTheDocument(); // NEXT_PUBLIC_TRIAL_RUNS=5 via vi.stubEnv
  });

  it("token mode keeps its own hero: Get started -> /settings, no request link, anchors point at /about", () => {
    sameOriginFlag.value = false;
    render(<Landing />);
    expect(screen.getByRole("link", { name: "Get started" })).toHaveAttribute("href", "/settings");
    expect(screen.getByRole("link", { name: "See how it works" })).toHaveAttribute("href", "/about#how");
    expect(screen.queryByRole("link", { name: /request beta access|tailor my resume/i })).toBeNull();
    expect(screen.getByText(/Free and open source \(AGPL-3\.0\)/)).toBeInTheDocument();
  });

  it("links to the detail instead of containing it", () => {
    const { container } = render(<Landing />);
    expect(screen.getByRole("link", { name: /how it works in detail/i })).toHaveAttribute("href", "/about");
    for (const moved of [/Why this exists/, /Why not just ask a chatbot/, /For developers/, /Before you start/, /What it costs/]) {
      expect(screen.queryByText(moved)).toBeNull();
    }
    expect(container.querySelector("#tour, #how, #honest, #developers")).toBeNull();
    expect(container.textContent).not.toMatch(/provenance|no-unverified-metrics/); // CaughtDemo's rules live on /about
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
