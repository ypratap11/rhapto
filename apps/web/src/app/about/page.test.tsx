import { render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import AboutPage from "./page";

// Review finding I3: About's primary CTA must be mode-aware, since /settings has nothing to
// connect to in access mode (N1 hides its only relevant card there). `SAME_ORIGIN_DEPLOYMENT` is a
// `const` computed from an env var at module load, so it can only be overridden through this module
// mock -- the same pattern TokenGate.test.tsx and settings/page.test.tsx use.
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

afterEach(() => {
  sameOriginFlag.value = false;
});

describe("AboutPage", () => {
  it("leads with what Rhapto is and a way in", () => {
    render(<AboutPage />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "A resume you can defend in any interview.",
    );
    expect(screen.getByRole("link", { name: /get started/i })).toHaveAttribute("href", "/settings");
  });

  it("points the hosted CTAs at /start, not the token-mode settings form", () => {
    sameOriginFlag.value = true;
    render(<AboutPage />);
    // Owner decision 2026-10-09: the hosted "Sign in" links became "Tailor my resume" -> /start (which
    // sits behind Cloudflare Access, so following it IS the sign-in flow). Hero and footer each have one.
    const tailorLinks = screen.getAllByRole("link", { name: /^tailor my resume$/i });
    expect(tailorLinks).toHaveLength(2);
    for (const link of tailorLinks) expect(link).toHaveAttribute("href", "/start");
    expect(screen.queryByRole("link", { name: /sign in/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /open your dashboard/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /^get started$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /connect your instance/i })).not.toBeInTheDocument();
  });

  it("lays out the journey as six beats, in order", () => {
    // Was "lays out exactly five numbered steps in order", pinning the five How it works cards. Those
    // cards were removed: they retold, a second time and more weakly, the journey the six animated
    // beats above them already tell. The shape assertion moves to the beats rather than disappearing.
    render(<AboutPage />);
    const beats = within(
      screen.getByRole("list", { name: /from asking for access to pressing send/i }),
    ).getAllByRole("listitem");
    expect(beats.map((li) => li.querySelector("button")?.firstElementChild?.textContent)).toEqual([
      "You ask for access",
      "You bring your resume",
      "You pick a track",
      "Jobs arrive and get scored",
      "Rhapto tailors one",
      "You review and send it",
    ]);
  });

  it("still describes where your data lives, for both deployments", () => {
    // This is the surviving half of the old five-steps test, re-pointed rather than dropped. It is a
    // privacy claim read by someone deciding whether to upload their CV. It once said only "it runs
    // on your machine - your resume and your key stay there", which is false for anyone invited onto
    // a hosted instance: their resume is in that server's database. Both deployments must be
    // described, so reinstating the half-true version still fails here. It now lives in its own
    // block beside the beats -- it was never a step, and nobody "does" it.
    render(<AboutPage />);
    const residency =
      screen.getByRole("heading", { name: /wherever you run it/i }).parentElement?.textContent ?? "";
    expect(residency).toMatch(/stay on your machine/i);
    expect(residency).toMatch(/what does leave, on every run, is the text/i);
    expect(residency).toMatch(/invited/i);
  });

  it("states the three guarantees that are the reason to use it", () => {
    render(<AboutPage />);
    expect(screen.getByText("Know where each claim came from")).toBeInTheDocument();
    expect(screen.getByText("Use numbers you can support")).toBeInTheDocument();
    expect(screen.getByText("The last click is yours")).toBeInTheDocument();
  });

  it("says what a resume costs before anyone spends money", () => {
    // Per-model costs moved, whole, into the developer section; the free-beta line is in the main flow
    // (About.test.tsx). Every regex below is unchanged.
    render(<AboutPage />);
    const costs = screen.getByText("What it costs").closest("[data-slot=card]");
    expect(costs).not.toBeNull();
    expect(costs).toHaveTextContent(/29–36¢/);
    expect(costs).toHaveTextContent(/AGPL-3\.0/);
    // The cheap model passed every guardrail and still dropped a whole role. Quoting its price
    // without that caveat would send people to the one path that can silently lose their history,
    // so the warning is part of the price — deleting it must fail a test, not pass review.
    expect(costs).toHaveTextContent(/left a whole role out/);
    // Completeness now catches a picked role going missing, but not one never picked; the old
    // "not missing ones" line would now understate the check, and overstating it would be worse.
    // The completeness guardrail (engine/guardrails/completeness.py) covers every selected block, on
    // model drafts only; the hand-edit PATCH skips it. Pin both halves so neither claim drifts.
    expect(costs).toHaveTextContent(/checks that every role it selected for the resume appears/);
    expect(costs).toHaveTextContent(/not your own hand edits/);
    expect(costs).toHaveTextContent(/a role it never selected is not flagged/);
    expect(costs).not.toHaveTextContent(/not missing ones/);
  });

  it("promises in plain words, once, that it never submits an application", () => {
    // Was /Submit an application/i on the will-not-do bullet. That bullet and the why-exists sentence
    // were dropped so the promise is said once, in the third card, the strongest instance.
    render(<AboutPage />);
    expect(screen.getByText(/no code path in it that submits an application/i)).toBeInTheDocument();
    expect(screen.getAllByText(/no code path/i)).toHaveLength(1);
  });
});
