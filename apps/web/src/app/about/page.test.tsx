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

  it("lays out exactly five numbered steps in order", () => {
    render(<AboutPage />);
    const steps = within(screen.getByRole("list", { name: /how it works/i })).getAllByRole(
      "listitem",
    );
    expect(steps.map((li) => li.querySelector("[data-slot=card-title]")?.textContent)).toEqual([
      "Get in",
      "Bring your resume",
      "Pick a track",
      "Let the jobs come to you",
      "Tailor, review, apply",
    ]);
    // Step 1 is a privacy claim, and it is read by someone deciding whether to upload their CV. It
    // once said only "it runs on your machine - your resume and your key stay there", which is false
    // for anyone invited onto a hosted instance: their resume is in that server's database. Both
    // deployments must be described, so reinstating the half-true version fails here.
    const first = steps[0]?.textContent ?? "";
    expect(first).toMatch(/nothing leaves your machine/i);
    expect(first).toMatch(/invited/i);
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
