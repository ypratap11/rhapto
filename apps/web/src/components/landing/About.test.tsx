import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ACCESS_REQUEST_EMAIL, ACCESS_REQUEST_MAILTO, ACCESS_REQUEST_URL } from "./access";
import { About } from "./About";

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

// The request URL ships empty (mailto fallback). To see the external-link branch render, `Landing`'s
// own call to `accessRequestLink()` is redirected to a test URL; the helper's logic is the real one.
const accessUrl = { value: "" };
vi.mock("./access", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./access")>();
  return {
    ...actual,
    accessRequestLink: (url?: string) => actual.accessRequestLink(url ?? accessUrl.value),
  };
});

beforeEach(() => vi.stubEnv("NEXT_PUBLIC_TRIAL_RUNS", "5"));

afterEach(() => {
  vi.unstubAllEnvs();
  sameOriginFlag.value = false;
  accessUrl.value = "";
});

describe("About, the full pitch", () => {
  it("hosted hero: Request beta access is the one button, the tour is a link, Tailor my resume is small text", () => {
    sameOriginFlag.value = true;
    render(<About />);

    // The hero is the first band on the page. Scoped to it, because that is where a stranger looks --
    // a page-wide query passes on the footer alone.
    const hero = screen.getAllByTestId("hero-band")[0]!;
    // The three calls to action, in order; "What that means" after them is the anchor to #honest.
    const links = within(hero).getAllByRole("link").slice(0, 3);
    expect(links.map((l) => l.textContent)).toEqual([
      "Request beta access",
      "Watch the 2-minute tour",
      "Tailor my resume",
    ]);

    const [request, tour, tailor] = links as HTMLAnchorElement[];
    expect(request).toHaveAttribute("href", ACCESS_REQUEST_MAILTO);
    expect(tour).toHaveAttribute("href", "#tour");
    expect(tailor).toHaveAttribute("href", "/start");
    // Hierarchy: only the request link is a filled button; the other two are plain text links.
    expect(request!.className).toMatch(/bg-primary/);
    expect(tour!.className).not.toMatch(/bg-primary|border-border/);
    expect(tailor!.className).not.toMatch(/bg-primary|border-border/);
    // "Already invited?" is the plain text that leads into the link.
    expect(tailor!.parentElement!.textContent).toMatch(/Already invited\?\s*Tailor my resume/);

    expect(screen.queryByRole("link", { name: /open your dashboard/i })).toBeNull();
    expect(screen.queryByRole("link", { name: /^request access$/i })).toBeNull();

    // Footer mirrors it, so the count stays two. Owner decision 2026-10-09: hosted About has no
    // "Sign in" link and nothing points at /dashboard.
    const tailorAll = screen.getAllByRole("link", { name: /^tailor my resume$/i });
    expect(tailorAll).toHaveLength(2);
    for (const link of tailorAll) expect(link).toHaveAttribute("href", "/start");
    expect(screen.queryAllByRole("link", { name: /sign in/i })).toHaveLength(0);
    for (const link of screen.getAllByRole("link")) expect(link).not.toHaveAttribute("href", "/dashboard");
    const requestAll = screen.getAllByRole("link", { name: /^request beta access$/i });
    expect(requestAll).toHaveLength(2);
    for (const link of requestAll) {
      expect(link).toHaveAttribute("href", ACCESS_REQUEST_MAILTO);
      // Mailto links open in place, with no target or rel.
      expect(link).not.toHaveAttribute("target");
      expect(link).not.toHaveAttribute("rel");
    }
    // Spelled out rather than only compared to the constant.
    expect(ACCESS_REQUEST_MAILTO).toBe(
      "mailto:hellorhapto@augaster.com?subject=Rhapto%20access%20request",
    );
    expect(ACCESS_REQUEST_EMAIL).toBe("hellorhapto@augaster.com");
  });

  it("with the shipped request URL, both request buttons open it in a new tab and the address is not printed", () => {
    sameOriginFlag.value = true;
    accessUrl.value = ACCESS_REQUEST_URL;
    render(<About />);
    const requestAll = screen.getAllByRole("link", { name: /^request beta access$/i });
    expect(requestAll).toHaveLength(2);
    for (const link of requestAll) {
      expect(link).toHaveAttribute("href", "https://forms.gle/1GUeGcKB9fCiJAdFA");
      expect(link).toHaveAttribute("target", "_blank");
      expect(link).toHaveAttribute("rel", "noreferrer");
    }
    expect(document.querySelectorAll('a[href^="mailto:"]')).toHaveLength(0);
    expect(document.body.textContent).not.toContain(ACCESS_REQUEST_EMAIL);
  });

  it("gives the tour section the #tour anchor, on Landing's wrapper", () => {
    render(<About />);
    const target = document.getElementById("tour");
    expect(target).not.toBeNull();
    expect(target!.tagName).toBe("SECTION");
    expect(target!.className).toMatch(/scroll-mt-20/);
    expect(within(target!).getByRole("region", { name: /product tour/i })).toBeInTheDocument();
    expect(document.querySelectorAll("#tour")).toHaveLength(1);
  });

  it("orders the page: hero, tour, why, chatbot, how it works, before you start, developers", () => {
    render(<About />);
    const at = (name: RegExp) => screen.getByRole("heading", { level: 2, name });
    const order = [
      screen.getByRole("heading", { level: 1 }),
      screen.getByRole("region", { name: /product tour/i }),
      at(/why this exists/i),
      at(/why not just ask a chatbot/i),
      at(/^how it works$/i),
      at(/before you start/i),
      at(/for developers & self-hosting/i),
    ];
    for (let i = 1; i < order.length; i++) {
      expect(
        order[i - 1]!.compareDocumentPosition(order[i]!) & Node.DOCUMENT_POSITION_FOLLOWING,
        `section ${i} follows section ${i - 1}`,
      ).toBeTruthy();
    }
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
  });

  it("says private beta in the hero with no pronoun and no turnaround, and keeps the allowlist truth under Before you start", () => {
    sameOriginFlag.value = true;
    render(<About />);
    const hero = screen.getAllByTestId("hero-band")[0]!;
    const line = within(hero).getByText(/Private beta: sign-in is invite-only, so request access first\./);
    // Nobody has committed to answering, so this line must not imply a turnaround or a grant.
    expect(line.textContent ?? "").not.toMatch(/reply|respond|get back|within \d|hour|business day|I'll|I will/i);
    // And no pronoun for the maintainer.
    expect(line.textContent ?? "").not.toMatch(/\b(him|her|his|hers|he|she|they|them|i)\b/i);
    // The mechanics moved, shortened, and stayed true: addresses not on the list are turned away.
    const before = screen.getByRole("heading", { name: /before you start/i }).closest("section")!;
    const mech = within(before).getByText(/sign-in is an allowlist the maintainer keeps by hand/i);
    expect(mech.textContent).toMatch(/not on it will be turned away/i);
    expect(mech.textContent ?? "").not.toMatch(/reply|respond|get back|within \d|hour|business day/i);
    expect(mech.textContent ?? "").not.toMatch(/\b(him|her|his|hers|he|she|they|them)\b/i);
  });

  it("offers a self-hoster neither sign-in nor request access, because they have nobody to ask", () => {
    render(<About />);
    expect(screen.getByRole("link", { name: /^get started$/i })).toHaveAttribute("href", "/settings");
    expect(screen.queryByRole("link", { name: /^sign in$/i })).toBeNull();
    expect(screen.queryByRole("link", { name: /request (beta )?access/i })).toBeNull();
    expect(screen.queryByText(/private beta/i)).toBeNull();
    // (Journey beat 1 still mentions the allowlist in both modes; that is outside this change.)
    const before = screen.getByRole("heading", { name: /before you start/i }).closest("section")!;
    expect(within(before).queryByText(/allowlist/i)).toBeNull();
    // No mailto at all: nothing on a self-hosted page should mail the maintainer of someone else's
    // instance.
    expect(document.querySelectorAll('a[href^="mailto:"]')).toHaveLength(0);
  });

  it("keeps the data-residency disclosure whole, for both audiences, now in the developer section", () => {
    // This assertion used to reach the "Get in" card via the How it works list. The cards were
    // removed as a duplicate telling of the journey, but card 1 was never really a step -- it is the
    // disclosure someone reads while deciding whether to upload a CV, and its wording was rewritten
    // after a shipped defect (a privacy claim true only for self-hosters, false for anyone on a
    // hosted instance). It moved; it did not die. Re-pointed, not deleted, and every clause is still
    // asserted, in both modes, since neither audience may lose its half.
    for (const hosted of [false, true]) {
      sameOriginFlag.value = hosted;
      const { unmount } = render(<About />);
      const heading = screen.getByRole("heading", { level: 3, name: /wherever you run it/i });
      // Moved word for word into "For developers & self-hosting".
      expect(heading.closest("section")).toBe(
        screen.getByRole("heading", { level: 2, name: /for developers & self-hosting/i }).closest("section"),
      );
      const block = heading.parentElement!.textContent!;
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
    render(<About />);
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
    render(<About />);
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
    // said once on the whole page
    expect(screen.getAllByText(/no code path/i)).toHaveLength(1);
    // the demo is in the hero, beside the copy
    expect(within(hero).getByText(/what happens inside a run/i)).toBeInTheDocument();
    // "A new account starts empty" keeps its place in the hero
    expect(within(hero).getByText(/A new account starts empty/i)).toBeInTheDocument();
  });

  it("uses the glow band, a 600-weight headline, and link-on-band for text links on it", () => {
    render(<About />);
    // /about renders two HeroBands (the second wraps ProductTour); the hero is the first.
    const band = screen.getAllByTestId("hero-band")[0]!;
    expect(band.className).toContain("bg-hero-glow");
    expect(screen.getByRole("heading", { level: 1 }).className).toContain("font-semibold");
    expect(band.querySelectorAll("a.text-primary")).toHaveLength(0);
  });

  it("goes two-column at lg, not md", () => {
    render(<About />);
    const hero = screen.getAllByTestId("hero-band")[0]!;
    const grid = hero.querySelector('[class*="lg:grid-cols-"]');
    expect(grid).not.toBeNull();
    expect(hero.innerHTML).not.toMatch(/md:grid-cols-\[/);
  });

  it("no longer overclaims: no 'refuses to do either', no 'cannot happen', no unconditional title/date promise", () => {
    const { container } = render(<About />);
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
    render(<About />);
    const card = screen.getByText("Use numbers you can support").closest("[data-slot='card']")!;
    expect(card.textContent).toMatch(/one try at a fix/i);
    expect(card.textContent).toMatch(/if that fails, the whole package is marked blocked/i);
  });

  it("benefit-led card titles, and the third card is kept whole", () => {
    render(<About />);
    expect(screen.getByText("Know where each claim came from")).toBeInTheDocument();
    expect(screen.getByText("Use numbers you can support")).toBeInTheDocument();
    const last = screen.getByText("The last click is yours").closest("[data-slot='card']")!;
    expect(last.textContent).toMatch(/no code path in it that submits an application/i);
    expect(screen.queryByText("Every line has a source")).toBeNull();
    expect(screen.queryByText("Numbers need your sign-off")).toBeNull();
  });

  it("makes the chatbot comparison precise, without 'shows you anything that fails' or 'catches everything'", () => {
    const { container } = render(<About />);
    const section = screen.getByRole("heading", { name: /why not just ask a chatbot/i }).closest("section")!;
    const t = section.textContent ?? "";
    expect(t).toMatch(/details you didn.t confirm/i);
    expect(t).toMatch(/numbers you haven.t confirmed/i);
    expect(t).toMatch(/one chance to fix/i);
    expect(t).toMatch(/marks the package blocked if the fix doesn.t hold/i);
    const all = container.textContent ?? "";
    expect(all).not.toMatch(/shows you anything that still fails/i);
    expect(all).not.toMatch(/catches everything/i);
    expect(all).not.toMatch(/happily invent/i);
  });

  it("names what Rhapto checks and what you still review, in the main flow", () => {
    render(<About />);
    const heading = screen.getByRole("heading", { name: /what rhapto checks — and what you still review/i });
    expect(heading.closest("section")).toBe(
      screen.getByRole("heading", { name: /why not just ask a chatbot/i }).closest("section"),
    );
  });

  it("says what the checks do not catch, next to the promises", () => {
    render(<About />);
    const line = screen.getByText(/What the checks do not catch/i);
    expect(line.textContent).toMatch(/stretch the wording of its source/i);
    // The completeness check keeps every role that was picked; one never picked is still not flagged,
    // so the limit stays on the page in that narrower form.
    expect(line.textContent).toMatch(/never selected for this resume is not\s+flagged as missing/i);
    expect(line.textContent).toMatch(/still read the\s+resume before you send it/i);
  });

  it("prints the request-access address as text, not only as a mailto href", () => {
    // A visitor with no registered mail handler gets a button that does nothing; without the address
    // in the copy there is no way to learn where to write, and this is the one path the whole change
    // exists to create.
    sameOriginFlag.value = true;
    render(<About />);
    const hero = screen.getAllByTestId("hero-band")[0]!;
    expect(within(hero).getByText(/private beta/i).textContent ?? "").toContain(ACCESS_REQUEST_EMAIL);
  });

  it("drops the redundant 'already set up' line in hosted mode, keeps it where it names a different page", () => {
    sameOriginFlag.value = true;
    const { unmount } = render(<About />);
    // In hosted mode the button beside it is "Tailor my resume" -> /start, so this sentence was a second,
    // contradictory framing of the same destination.
    expect(screen.queryByText(/Already set up\?/i)).toBeNull();
    unmount();

    sameOriginFlag.value = false;
    render(<About />);
    // In token mode the button goes to /settings, so it genuinely names somewhere else.
    expect(screen.getByText(/Already set up\?/i)).toBeInTheDocument();
  });

  it("pricing: hosted says 5 AI runs on us, first import is free, paid plan coming; token mode says free and open source", () => {
    sameOriginFlag.value = true;
    const { container, unmount } = render(<About />);
    const before = screen.getByRole("heading", { name: /before you start/i }).closest("section")!;
    const hosted = within(before).getByText(/Free during the beta/i).closest("[data-slot='card']")!;
    expect(hosted.textContent).toMatch(/5 AI runs on us \(your first resume import is free\)/);
    expect(hosted.textContent).toMatch(/then use your own AI key/i);
    expect(hosted.textContent).toMatch(/A paid plan with AI usage included is coming/i);
    expect(container.textContent).not.toMatch(/\d tailored resumes/i);
    expect(container.textContent).not.toMatch(/3 AI runs/);
    expect(container.textContent).not.toMatch(/no subscription/i);
    unmount();

    sameOriginFlag.value = false;
    const r = render(<About />);
    const t = r.container.textContent ?? "";
    expect(t).toMatch(/Free and open source \(AGPL-3\.0\); you use your own AI key/);
    expect(t).not.toMatch(/AI runs on us/i);
    expect(t).not.toMatch(/paid plan/i);
    expect(t).not.toMatch(/free runs|this beta/i);
  });

  it("privacy one-liner: hosted names the beta's provider for free runs, token mode does not", () => {
    sameOriginFlag.value = true;
    const { unmount } = render(<About />);
    const line = screen.getByText(/Your documents and career record stay in your account\./);
    expect(line.textContent).toMatch(
      /To draft, Rhapto sends text from them to one AI provider: this beta.s during your free runs, then yours\./,
    );
    // the will-not-do key bullet is fixed the same way
    expect(screen.getByText(/Send your resume, your key, or your history anywhere except/i).textContent).toMatch(
      /this beta.s during your free runs, then yours/,
    );
    unmount();

    sameOriginFlag.value = false;
    render(<About />);
    const tokenLine = screen.getByText(/Your documents and career record stay in your account\./);
    expect(tokenLine.textContent).toMatch(/one AI provider/i);
    expect(tokenLine.textContent).not.toMatch(/beta|free runs/i);
    expect(
      screen.getByText(/Send your resume, your key, or your history anywhere except/i).textContent,
    ).not.toMatch(/beta|free runs/i);
  });

  it("keeps the client boundary in the children, not in About", () => {
    // `Landing` is mounted at `/about` as a server component. A hook added directly to it fails at
    // build time, not in jsdom, so the only way a unit test can pin this constraint is to read the
    // modules: the interactivity must live behind its own "use client", as ProductTour already
    // does. Cheap, and it fails the moment someone reaches for `useState` in Landing.
    const dir = dirname(fileURLToPath(import.meta.url));
    const read = (name: string) => readFileSync(join(dir, name), "utf8");
    // Comments stripped first: Landing's own comments discuss `"use client"` and would otherwise
    // make this pass or fail on prose rather than on code.
    const code = read("About.tsx")
      .replace(/\/\*[\s\S]*?\*\//g, "")
      .replace(/^[ \t]*\/\/.*$/gm, "");
    expect(code).not.toMatch(/"use client"/);
    expect(code).not.toMatch(/\buse[A-Z]\w*\(/);
    for (const child of ["JourneyWalkthrough.tsx", "ProductTour.tsx", "CaughtDemo.tsx"]) {
      expect(read(child)).toMatch(/^"use client";/);
    }
  });
});
