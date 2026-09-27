import { render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import AboutPage from "./page";

// Review finding I3: Landing's primary CTA must be mode-aware, since /settings has nothing to
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
      "Every application, stitched to fit.",
    );
    expect(screen.getByRole("link", { name: /get started/i })).toHaveAttribute("href", "/settings");
  });

  it("points the primary CTAs at the dashboard in access mode, not the token-mode settings form", () => {
    sameOriginFlag.value = true;
    render(<AboutPage />);
    // Both the hero and footer CTAs are mode-aware (Landing.tsx). The href is the assertion this
    // test was added for (review finding I3: /settings has nothing to connect in access mode); the
    // label is now "Sign in" rather than "Open your dashboard", because /dashboard sits behind
    // Cloudflare Access and following it IS the sign-in flow the page had been telling people to use
    // while offering them no way to do it. The route, and therefore this test's point, is unchanged.
    const dashboardLinks = screen.getAllByRole("link", { name: /^sign in$/i });
    expect(dashboardLinks).toHaveLength(2);
    for (const link of dashboardLinks) expect(link).toHaveAttribute("href", "/dashboard");
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
    expect(screen.getByText("Every line has a source")).toBeInTheDocument();
    expect(screen.getByText("Numbers need your sign-off")).toBeInTheDocument();
    expect(screen.getByText("The last click is yours")).toBeInTheDocument();
  });

  it("says what a resume costs before anyone spends money", () => {
    // The project funds nobody's API usage, so the price belongs on the way in, not in a FAQ.
    render(<AboutPage />);
    const costs = screen.getByText("What it costs").closest("[data-slot=card]");
    expect(costs).not.toBeNull();
    expect(costs).toHaveTextContent(/29–36¢/);
    expect(costs).toHaveTextContent(/AGPL-3\.0/);
    // The cheap model passed every guardrail and still dropped a whole role. Quoting its price
    // without that caveat would send people to the one path that can silently lose their history,
    // so the warning is part of the price — deleting it must fail a test, not pass review.
    expect(costs).toHaveTextContent(/left a whole role out/);
  });

  it("promises in plain words that it never submits an application", () => {
    render(<AboutPage />);
    expect(screen.getByText(/Submit an application/i)).toBeInTheDocument();
  });
});
