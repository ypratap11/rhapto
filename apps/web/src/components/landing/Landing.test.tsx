import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import visibility from "@/lib/edge-visibility.json";
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

vi.mock("next/link", () => ({
  default: ({ prefetch, href, children, ...rest }: { prefetch?: boolean | null; href: string; children: React.ReactNode } & Record<string, unknown>) => (
    <a href={href} data-link="1" data-prefetch={String(prefetch)} {...rest}>
      {children}
    </a>
  ),
}));

beforeEach(() => vi.stubEnv("NEXT_PUBLIC_TRIAL_RUNS", "5"));

afterEach(() => {
  vi.unstubAllEnvs();
  sameOriginFlag.value = true;
});

describe("Landing, the light front door", () => {
  it("has a hero, a tour, three steps, one proof and a closing call to action", () => {
    const { container } = render(<Landing />);
    expect(screen.getAllByTestId("hero-band")).toHaveLength(1);
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(container.querySelectorAll("section")).toHaveLength(4); // tour + steps + proof + closing; the hero is a band
    const steps = within(screen.getByRole("list", { name: /three steps/i })).getAllByRole("listitem");
    expect(steps.map((li) => li.textContent)).toEqual([
      expect.stringContaining("Upload your resume"),
      expect.stringContaining("Pick a job"),
      expect.stringContaining("Download your tailored resume"),
    ]);
    expect(screen.getByText("Rhapto stopped this draft: 45 is not in your resume.")).toBeInTheDocument();
  });

  it("hosted: Tailor my resume -> /start; request-access appears in the hero and the closing CTA only (not under the tour); no Sign in", () => {
    const { container } = render(<Landing />);
    const hero = screen.getByTestId("hero-band");
    const cta = within(hero).getByRole("link", { name: "Tailor my resume" }); // the arrow span is aria-hidden
    expect(cta).toHaveAttribute("href", "/start");
    expect(cta.className).toMatch(/bg-primary/);
    expect(cta.className).toContain("shadow-cta");
    expect(cta.className).toContain("cta-lift");
    const requests = screen.getAllByRole("link", { name: "Request beta access" });
    expect(requests).toHaveLength(2); // hero + closing; the site footer is in Shell
    expect(within(hero).getAllByRole("link", { name: "Request beta access" })).toHaveLength(1);
    expect(within(container.querySelector("section#tour") as HTMLElement).queryByRole("link", { name: "Request beta access" })).toBeNull();
    expect(requests[0]).toHaveAttribute("href", ACCESS_REQUEST_URL || ACCESS_REQUEST_MAILTO);
    if (ACCESS_REQUEST_URL) expect(requests[0]).toHaveAttribute("target", "_blank");
    expect(requests[0]!.className).not.toMatch(/bg-primary/);
    expect(screen.queryByRole("link", { name: /sign in/i })).toBeNull();
    expect(screen.getAllByText("No invite yet?", { exact: false })).toHaveLength(2);
    expect(within(hero).getByText(/first resume import and 5 AI runs are on us/)).toBeInTheDocument();
  });

  it("has no 'See how it works' link: the tour is directly below", () => {
    render(<Landing />);
    expect(screen.queryByRole("link", { name: /See how it works/ })).toBeNull();
  });

  it("token mode keeps its own hero: Get started -> /settings, no request link", () => {
    sameOriginFlag.value = false;
    render(<Landing />);
    expect(within(screen.getByTestId("hero-band")).getByRole("link", { name: "Get started" })).toHaveAttribute("href", "/settings");
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

  it("hero copy: headline, subline, one facts line, free-limit line; no badge", () => {
    render(<Landing />);
    expect(screen.getByText(/first resume import and 5 AI runs are on us/)).toBeInTheDocument();
    expect(screen.getByText("Upload your resume, pick a job, and get your own document rewritten for it.")).toBeInTheDocument();
    expect(screen.getByText("Open source · You always submit · Every number checked")).toBeInTheDocument();
    expect(screen.queryByText("Every number checked against your resume")).toBeNull();
    expect(screen.queryByText(/Your own document$/)).toBeNull();
    expect(screen.getByRole("heading", { level: 1 }).className).toContain("font-semibold");
    expect(screen.getByText("defend").tagName).toBe("SPAN");
    expect(screen.getByText("defend").className).toContain("highlight-underline");
  });

  it("is centred on one content width and one section rhythm", () => {
    const { container } = render(<Landing />);
    const hero = screen.getByTestId("hero-band");
    expect((hero.firstElementChild as HTMLElement).className).toContain("max-w-5xl");
    expect(screen.getByRole("heading", { level: 1 }).parentElement!.className).toContain("items-center");
    for (const sel of ["section#tour", "section[aria-labelledby='steps-heading']", "section[aria-labelledby='proof-heading']", "section[aria-labelledby='closing-heading']"]) {
      const el = container.querySelector(sel) as HTMLElement;
      expect(el.className, sel).toContain("mx-auto");
      expect(el.className, sel).toContain("max-w-5xl");
    }
    for (const sel of ["section[aria-labelledby='steps-heading']", "section[aria-labelledby='proof-heading']"]) {
      expect((container.querySelector(sel) as HTMLElement).className, sel).toMatch(/\bmb-16\b.*\bsm:mb-20\b|\bsm:mb-20\b.*\bmb-16\b/);
    }
    expect((container.querySelector("section[aria-labelledby='closing-heading']") as HTMLElement).className).toContain("sm:mb-12"); // + main's pb-8 = the same gap before the footer
    expect(container.querySelector("[data-decor]")).toBeNull();
  });

  it("steps: visible centred heading; one number per card (circle aria-hidden, text prefix sr-only)", () => {
    render(<Landing />);
    const h = screen.getByRole("heading", { level: 2, name: "Three steps to a resume you can defend" });
    expect(h.className).not.toContain("sr-only");
    expect(h.className).toContain("text-center");
    const items = within(screen.getByRole("list", { name: /three steps/i })).getAllByRole("listitem");
    items.forEach((li, i) => {
      expect(li.className).toContain("text-center");
      expect(li.querySelector("[aria-hidden='true']")!.textContent).toBe(String(i + 1));
      const prefix = [...li.querySelectorAll("span")].find((s) => s.textContent === `${i + 1}. `)!;
      expect(prefix.className).toContain("sr-only");
    });
  });

  it.each([true, false])("closing call to action (hosted=%s): verbatim copy, same target as the hero, request link hosted-only", (hosted) => {
    sameOriginFlag.value = hosted;
    const { container } = render(<Landing />);
    const closing = container.querySelector("section[aria-labelledby='closing-heading']") as HTMLElement;
    expect(within(closing).getByRole("heading", { level: 2, name: "Try it on your own resume" })).toBeInTheDocument();
    expect(within(closing).getByText("Upload a Word file, pick a job, and read the result before you send anything.")).toBeInTheDocument();
    const hero = screen.getByTestId("hero-band");
    const heroCta = within(hero).getByRole("link", { name: hosted ? /Tailor my resume/ : /Get started/ });
    const cta = within(closing).getByRole("link", { name: hosted ? /Tailor my resume/ : /Get started/ });
    expect(cta.getAttribute("href")).toBe(heroCta.getAttribute("href"));
    expect(cta.getAttribute("href")).toBe(hosted ? "/start" : "/settings");
    expect(cta.className).toContain("cta-lift");
    expect(closing.className).toContain("bg-band-peach");
    const req = within(closing).queryByRole("link", { name: "Request beta access" });
    expect(!!req).toBe(hosted);
    expect(closing.textContent).not.toMatch(CLAIM);
  });

  it("steps, proof and closing fade up on entry (class `reveal`); the hero and tour do not", () => {
    const { container } = render(<Landing />);
    for (const sel of ["steps-heading", "proof-heading", "closing-heading"]) {
      expect((container.querySelector(`section[aria-labelledby='${sel}']`) as HTMLElement).className).toContain("reveal");
    }
    expect((container.querySelector("section#tour") as HTMLElement).className).not.toContain("reveal");
  });

  it("the reveal CSS hides only inside a no-preference block (content is visible without JS); no scrubbing timeline; CTA lift is cancelled under reduce", () => {
    const css = readFileSync(join(dirname(fileURLToPath(import.meta.url)), "..", "..", "app", "globals.css"), "utf8");
    const armed = css.indexOf('[data-reveal="armed"]');
    expect(armed).toBeGreaterThan(-1);
    expect(css.indexOf('[data-reveal="armed"]')).toBe(css.lastIndexOf('[data-reveal="armed"]')); // exactly one rule
    const media = css.lastIndexOf("@media (prefers-reduced-motion: no-preference)", armed);
    expect(media).toBeGreaterThan(-1);
    expect(css.slice(media, armed)).not.toMatch(/\n\}\n/); // the media block has not closed before the armed rule
    expect(css).not.toContain("animation-timeline"); // the reveal runs once; a scroll timeline would re-hide on scroll-up
    const reduce = css.slice(css.indexOf("@media (prefers-reduced-motion: reduce)"));
    expect(reduce).toContain(".cta-lift:hover");
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

function prefetchedProtectedLinks(root: ParentNode): string[] {
  const protectedHref = (h: string | null) => !!h && visibility.protectedAtEdge.some((p) => h === p || h.startsWith(`${p}/`) || h.startsWith(`${p}#`));
  return [...root.querySelectorAll<HTMLAnchorElement>("a[data-link]")]
    .filter((a) => protectedHref(a.getAttribute("href")))
    .filter((a) => a.getAttribute("data-prefetch") !== "false")
    .map((a) => a.getAttribute("href")!);
}

describe("no prefetch of protected routes from /", () => {
  it.each([true, false])("every Link to a protected route on / has prefetch={false} (hosted=%s)", (hosted) => {
    sameOriginFlag.value = hosted;
    const { container } = render(<Landing />);
    expect(container.querySelectorAll("a[data-link]").length).toBeGreaterThanOrEqual(2); // hero + closing CTA
    expect(prefetchedProtectedLinks(container)).toEqual([]);
  });

  it("the helper FAILS on a bare Link to /start (proof the check can fail)", () => {
    const { container } = render(<a href="/start" data-link="1" data-prefetch="undefined">x</a>);
    expect(prefetchedProtectedLinks(container)).toEqual(["/start"]);
  });
});
