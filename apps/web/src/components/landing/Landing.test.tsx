import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ACCESS_REQUEST_EMAIL, ACCESS_REQUEST_MAILTO } from "./access";
import { Landing } from "./Landing";

// `SAME_ORIGIN_DEPLOYMENT` is a `const` computed from an env var at module load, so a module mock is
// the only way to exercise both deployments -- the same pattern about/page.test.tsx and
// TokenGate.test.tsx use.
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

describe("Landing, the way in", () => {
  it("offers a stranger on the hosted instance both a sign-in and a way to ask for access", () => {
    sameOriginFlag.value = true;
    render(<Landing />);

    // The defect this fixes: the page told people to sign in and had no sign-in anywhere, and its
    // only CTA led to a Cloudflare Access prompt that refuses an address nobody has allowlisted.
    // Scoped to the hero rather than to the page, because that is where a stranger looks -- a
    // page-wide query passes on the footer pair alone, which is how a weaker version of this
    // assertion survived putting "Open your dashboard" back in the hero.
    // The hero is the first band on the page; the other two are the product tour and How it works.
    const hero = screen.getAllByTestId("hero-band")[0]!;
    expect(within(hero).getByRole("link", { name: /^sign in$/i })).toHaveAttribute(
      "href",
      "/dashboard",
    );
    expect(within(hero).getByRole("link", { name: /^request access$/i })).toHaveAttribute(
      "href",
      ACCESS_REQUEST_MAILTO,
    );
    expect(screen.queryByRole("link", { name: /open your dashboard/i })).toBeNull();

    // And again at the foot of the page, so someone who read the whole thing does not scroll back.
    const signIn = screen.getAllByRole("link", { name: /^sign in$/i });
    expect(signIn).toHaveLength(2);
    for (const link of signIn) expect(link).toHaveAttribute("href", "/dashboard");

    const request = screen.getAllByRole("link", { name: /^request access$/i });
    expect(request).toHaveLength(2);
    for (const link of request) expect(link).toHaveAttribute("href", ACCESS_REQUEST_MAILTO);
    // Spelled out rather than only compared to the constant: a typo'd or emptied address would
    // otherwise agree with itself and pass.
    expect(ACCESS_REQUEST_MAILTO).toBe(
      "mailto:hellorhapto@augaster.com?subject=Rhapto%20access%20request",
    );
    expect(ACCESS_REQUEST_EMAIL).toBe("hellorhapto@augaster.com");
  });

  it("says that access is invite-only, next to the buttons, instead of letting Cloudflare Access refuse people unexplained", () => {
    sameOriginFlag.value = true;
    render(<Landing />);
    const line = screen.getByText(/sign-in is an allowlist the maintainer keeps by hand/i);
    expect(line).toBeInTheDocument();
    // Nobody has committed to answering, so this line must not imply a turnaround.
    expect(line.textContent ?? "").not.toMatch(/reply|respond|get back|within \d|hour|business day/i);
    // And no pronoun for the maintainer: the page never names them and states nobody's pronouns.
    expect(line.textContent ?? "").not.toMatch(/\b(him|her|his|hers|he|she|they|them)\b/i);
  });

  it("offers a self-hoster neither sign-in nor request access, because they have nobody to ask", () => {
    render(<Landing />);
    expect(screen.getByRole("link", { name: /^get started$/i })).toHaveAttribute("href", "/settings");
    expect(screen.queryByRole("link", { name: /^sign in$/i })).toBeNull();
    expect(screen.queryByRole("link", { name: /request access/i })).toBeNull();
    // No mailto at all: nothing on a self-hosted page should mail the maintainer of someone else's
    // instance.
    expect(document.querySelectorAll('a[href^="mailto:"]')).toHaveLength(0);
  });

  it("keeps the data-residency disclosure whole, for both audiences, after the five cards went", () => {
    // This assertion used to reach the "Get in" card via the How it works list. The cards were
    // removed as a duplicate telling of the journey, but card 1 was never really a step -- it is the
    // disclosure someone reads while deciding whether to upload a CV, and its wording was rewritten
    // after a shipped defect (a privacy claim true only for self-hosters, false for anyone on a
    // hosted instance). It moved; it did not die. Re-pointed, not deleted, and every clause is still
    // asserted, in both modes, since neither audience may lose its half.
    for (const hosted of [false, true]) {
      sameOriginFlag.value = hosted;
      const { unmount } = render(<Landing />);
      const block = screen
        .getByRole("heading", { name: /wherever you run it/i })
        .parentElement!.textContent!;
      expect(block).toMatch(/stay on your machine/i);
      // The exception is load-bearing: a privacy claim that omits what IS sent is the defect this
      // sentence shipped with. It must keep naming the model provider and that it happens per run.
      expect(block).toMatch(/what does leave, on every run, is the text/i);
      expect(block).toMatch(/model provider\s+you chose/i);
      expect(block).toMatch(/invited to/i);
      expect(block).toMatch(/your data lives on that server, encrypted/i);
      expect(block).toMatch(/walled off from every other account/i);
      expect(block).toMatch(/the only usage you pay for is your own/i);
      unmount();
    }
  });

  it("tells the journey once: six beats, no second telling underneath them", () => {
    render(<Landing />);
    const journey = screen.getByRole("list", { name: /from asking for access to pressing send/i });
    expect(within(journey).getAllByRole("listitem")).toHaveLength(6);
    // The five cards said the same thing a second time and the paragraph between them existed only
    // to excuse that. Both are gone, and neither may come back quietly.
    expect(screen.queryByRole("list", { name: /how it works/i })).toBeNull();
    expect(screen.queryByText(/five steps rather than six/i)).toBeNull();
    // The section keeps an orienting sentence, though -- losing it left the h2 running straight into
    // the animation with no prose at all.
    expect(screen.getByText(/Six beats from a cold install/i)).toBeInTheDocument();
  });

  it("leads with the catch: plain headline, the kicker, and a lede that says what happens inside a run", () => {
    render(<Landing />);
    const hero = screen.getAllByTestId("hero-band")[0]!;
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "A resume you can defend in any interview.",
    );
    // plain: no single-word colour accent inside the headline
    expect(screen.getByRole("heading", { level: 1 }).children).toHaveLength(0);
    expect(
      within(hero).getByText("Tailored for each job, with every line checked against your own record."),
    ).toBeInTheDocument();
    const lede = within(hero).getByText(/drafts your resume with an AI model and checks the draft/i);
    expect(lede.textContent).toMatch(/one fix/i);
    expect(lede.textContent).toMatch(/blocked/i);
    expect(lede.textContent).toMatch(/you press\s+submit/i);
    // the demo is in the hero, beside the copy
    expect(within(hero).getByText(/what happens inside a run/i)).toBeInTheDocument();
    // "A new account starts empty" keeps its place in the hero
    expect(within(hero).getByText(/A new account starts empty/i)).toBeInTheDocument();
  });

  it("goes two-column at lg, not md", () => {
    render(<Landing />);
    const hero = screen.getAllByTestId("hero-band")[0]!;
    const grid = hero.querySelector('[class*="lg:grid-cols-"]');
    expect(grid).not.toBeNull();
    expect(hero.innerHTML).not.toMatch(/md:grid-cols-\[/);
  });

  it("no longer overclaims: no 'refuses to do either', no 'cannot happen', no unconditional title/date promise", () => {
    const { container } = render(<Landing />);
    const text = container.textContent ?? "";
    expect(text).not.toMatch(/refuses to do either/i);
    expect(text).not.toMatch(/so that cannot happen/i);
    expect(text).not.toMatch(/not already in a block you wrote/i);
    expect(text).not.toMatch(/refusal you can switch on/i);
    expect(text).not.toMatch(/blocked before this document was produced/i);
    // only metrics and provenance may be called unconditional; entities is on by default
    expect(text).toMatch(/those two checks\s+always run/i);
    expect(text).toMatch(/on\s+by default/i);
  });

  it("says a failed number check first gets one fix, and blocks only if that fails", () => {
    render(<Landing />);
    const card = screen.getByText("Numbers need your sign-off").closest("[data-slot='card']")!;
    expect(card.textContent).toMatch(/one try at a fix/i);
    expect(card.textContent).toMatch(/if that fails, the whole package is marked blocked/i);
  });

  it("says what the checks do not catch, next to the promises", () => {
    render(<Landing />);
    const line = screen.getByText(/What the checks do not catch/i);
    expect(line.textContent).toMatch(/stretch the wording of its source/i);
    expect(line.textContent).toMatch(/still read the\s+resume before you send it/i);
  });

  it("prints the request-access address as text, not only as a mailto href", () => {
    // A visitor with no registered mail handler gets a button that does nothing; without the address
    // in the copy there is no way to learn where to write, and this is the one path the whole change
    // exists to create.
    sameOriginFlag.value = true;
    render(<Landing />);
    expect(screen.getByText(/sign-in is an allowlist/i).textContent ?? "").toContain(
      ACCESS_REQUEST_EMAIL,
    );
  });

  it("drops the redundant 'already set up' line in hosted mode, keeps it where it names a different page", () => {
    sameOriginFlag.value = true;
    const { unmount } = render(<Landing />);
    // In hosted mode the button beside it is "Sign in" -> /dashboard, so this sentence was a second,
    // contradictory framing of the same destination.
    expect(screen.queryByText(/Already set up\?/i)).toBeNull();
    unmount();

    sameOriginFlag.value = false;
    render(<Landing />);
    // In token mode the button goes to /settings, so it genuinely names somewhere else.
    expect(screen.getByText(/Already set up\?/i)).toBeInTheDocument();
  });

  it("keeps the client boundary in the children, not in Landing", () => {
    // `Landing` is mounted at `/about` as a server component. A hook added directly to it fails at
    // build time, not in jsdom, so the only way a unit test can pin this constraint is to read the
    // modules: the interactivity must live behind its own "use client", as ProductTour already
    // does. Cheap, and it fails the moment someone reaches for `useState` in Landing.
    const dir = dirname(fileURLToPath(import.meta.url));
    const read = (name: string) => readFileSync(join(dir, name), "utf8");
    // Comments stripped first: Landing's own comments discuss `"use client"` and would otherwise
    // make this pass or fail on prose rather than on code.
    const code = read("Landing.tsx")
      .replace(/\/\*[\s\S]*?\*\//g, "")
      .replace(/^[ \t]*\/\/.*$/gm, "");
    expect(code).not.toMatch(/"use client"/);
    expect(code).not.toMatch(/\buse[A-Z]\w*\(/);
    for (const child of ["JourneyWalkthrough.tsx", "ProductTour.tsx", "CaughtDemo.tsx"]) {
      expect(read(child)).toMatch(/^"use client";/);
    }
  });
});
