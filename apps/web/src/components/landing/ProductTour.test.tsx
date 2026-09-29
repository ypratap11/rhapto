import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ACCESS_REQUEST_MAILTO } from "./access";
import { ProductTour } from "./ProductTour";
import { CHAPTERS, STEPS, TOUR_H, TOUR_W, layout } from "./tourSteps";

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

function stubMatchMedia(reduce: boolean) {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: reduce && query.includes("prefers-reduced-motion"),
    media: query,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  })) as unknown as typeof window.matchMedia;
}

beforeEach(() => stubMatchMedia(false));
afterEach(() => {
  sameOriginFlag.value = false;
  vi.restoreAllMocks();
  Reflect.deleteProperty(window, "matchMedia");
});

const start = () => screen.getByRole("button", { name: /start the tour/i });
const title = () => screen.getByRole("heading", { level: 3 });
const next = () => screen.getByRole("button", { name: /^(next|finish)$/i });

async function toStep(user: ReturnType<typeof userEvent.setup>, n: number) {
  await user.click(start());
  for (let i = 0; i < n; i++) await user.click(next());
}

describe("ProductTour, at rest", () => {
  it("opens on the intro: an h2, the disclosure, no picture, no hotspot", () => {
    const { container } = render(<ProductTour />);
    expect(screen.getByRole("heading", { level: 2 })).toHaveTextContent(
      "A resume you can defend in any interview.",
    );
    expect(screen.queryByRole("heading", { level: 1 })).toBeNull();
    // Visible text, not a tooltip: the visitor must be told Maya is fictional and the rest is real.
    expect(
      screen.getByText(/Maya Chen is a fictional demo person\. Everything else is real/i),
    ).toBeVisible();
    expect(screen.getByText(/captured 29 September 2026/i)).toBeInTheDocument();
    // Payload: the intro covers the stage, so it must not download a screenshot.
    expect(container.querySelectorAll("img")).toHaveLength(0);
    expect(screen.queryByRole("button", { name: /^next:/i })).toBeNull();
    expect(screen.getByRole("region", { name: /product tour/i })).toBeInTheDocument();
  });

  it("has no brand header of its own", () => {
    render(<ProductTour />);
    expect(screen.queryByText(/^Rhapto$/)).toBeNull();
  });
});

describe("ProductTour, walking the steps", () => {
  it("Start shows step 1 with its picture, counter and title", async () => {
    const user = userEvent.setup();
    const { container } = render(<ProductTour />);
    await user.click(start());
    expect(title()).toHaveTextContent(STEPS[0]!.title);
    expect(screen.getByText(/1 of 14/)).toBeInTheDocument();
    const img = container.querySelector("img")!;
    expect(img).toHaveAttribute("src", "/tour/01.webp");
    expect(img).toHaveAttribute("alt", STEPS[0]!.title);
    expect(img).toHaveAttribute("width", String(TOUR_W));
    expect(img).toHaveAttribute("height", String(TOUR_H));
    expect(container.querySelectorAll("img")).toHaveLength(1);
  });

  it("the hotspot is a real button named for the next step, and advances", async () => {
    const user = userEvent.setup();
    render(<ProductTour />);
    await user.click(start());
    const hot = screen.getByRole("button", { name: `Next: ${STEPS[1]!.title}` });
    expect(hot.tagName).toBe("BUTTON");
    await user.click(hot);
    expect(title()).toHaveTextContent(STEPS[1]!.title);
    expect(screen.getByText(/2 of 14/)).toBeInTheDocument();
  });

  it("Next and Back move one step; Back on step 1 returns to the intro and focuses Start", async () => {
    const user = userEvent.setup();
    render(<ProductTour />);
    await toStep(user, 2);
    expect(title()).toHaveTextContent(STEPS[2]!.title);
    await user.click(screen.getByRole("button", { name: /^back$/i }));
    expect(title()).toHaveTextContent(STEPS[1]!.title);
    await user.click(screen.getByRole("button", { name: /^back$/i }));
    await user.click(screen.getByRole("button", { name: /^back$/i }));
    expect(start()).toHaveFocus();
    expect(screen.getByRole("heading", { level: 2 })).toBeInTheDocument();
  });

  it("a chapter click jumps to that chapter's first step and marks it current", async () => {
    const user = userEvent.setup();
    render(<ProductTour />);
    await user.click(start());
    const rail = screen.getByRole("navigation", { name: /chapters/i });
    const buttons = within(rail).getAllByRole("button");
    expect(buttons).toHaveLength(CHAPTERS.length);
    await user.click(buttons[3]!);
    const first = STEPS.findIndex((s) => s.c === 3);
    expect(title()).toHaveTextContent(STEPS[first]!.title);
    expect(buttons[3]).toHaveAttribute("aria-current", "step");
    expect(buttons[0]).not.toHaveAttribute("aria-current");
  });

  it("every step has an image with its title as alt text, in the /tour/NN.webp naming", async () => {
    const user = userEvent.setup();
    const { container } = render(<ProductTour />);
    await user.click(start());
    for (let i = 0; i < STEPS.length; i++) {
      const img = container.querySelector("img")!;
      expect(img.getAttribute("src")).toBe(`/tour/${String(i + 1).padStart(2, "0")}.webp`);
      expect(img.getAttribute("alt")).toBe(STEPS[i]!.title);
      if (i < STEPS.length - 1) await user.click(next());
    }
  });

  it("warms the next two pictures on start, not all fourteen", async () => {
    const seen: string[] = [];
    class FakeImage {
      set src(v: string) {
        seen.push(v);
      }
    }
    vi.stubGlobal("Image", FakeImage);
    const user = userEvent.setup();
    render(<ProductTour />);
    expect(seen).toHaveLength(0);
    await user.click(start());
    expect(seen).toEqual(["/tour/02.webp", "/tour/03.webp"]);
    vi.unstubAllGlobals();
  });

  it("the caption is structured: bold segments render as <strong>, and no markup is injected", async () => {
    const user = userEvent.setup();
    const { container } = render(<ProductTour />);
    await user.click(start());
    const live = container.querySelector('[aria-live="polite"]')!;
    expect(within(live as HTMLElement).getByText("blocks").tagName).toBe("STRONG");
    const src = readFileSync(
      join(dirname(fileURLToPath(import.meta.url)), "ProductTour.tsx"),
      "utf8",
    );
    expect(src).not.toMatch(/dangerouslySetInnerHTML/);
  });

  it("announces politely, and the live region holds the counter, title and body but no buttons", async () => {
    const user = userEvent.setup();
    const { container } = render(<ProductTour />);
    await user.click(start());
    const live = container.querySelector('[aria-live="polite"]') as HTMLElement;
    expect(live).not.toBeNull();
    expect(within(live).getByText(/1 of 14/)).toBeInTheDocument();
    expect(within(live).getByRole("heading", { level: 3 })).toBeInTheDocument();
    expect(within(live).queryAllByRole("button")).toHaveLength(0);
  });

  it("copy says what is true: the edited claims, not the old ones", async () => {
    const user = userEvent.setup();
    render(<ProductTour />);
    await user.click(start());
    expect(screen.getByText(/has to cite one of these/i)).toBeInTheDocument();
    expect(screen.queryByText(/and nothing else/i)).toBeNull();
    await user.click(next());
    expect(screen.getByText(/checks won't let that number through/i)).toBeInTheDocument();
    expect(screen.queryByText(/can't appear on any resume/i)).toBeNull();
    await user.click(next());
    expect(screen.getByText(/Her first search pulled/i)).toBeInTheDocument();
    expect(screen.getByText("28 live jobs")).toBeInTheDocument();
    for (let i = 0; i < 6; i++) await user.click(next());
    expect(screen.getByText("35% less ticket triage time")).toBeInTheDocument();
    expect(screen.queryByText(/faster/i)).toBeNull();
    for (let i = 0; i < 3; i++) await user.click(next());
    expect(screen.getByText(/It didn't invent experience to fit\./)).toBeInTheDocument();
  });
});

describe("ProductTour, the outro", () => {
  async function toOutro(user: ReturnType<typeof userEvent.setup>) {
    await toStep(user, STEPS.length - 1);
    await user.click(screen.getByRole("button", { name: /^finish$/i }));
  }

  it("Finish shows the four stats captioned as this run, and focuses the outro heading", async () => {
    const user = userEvent.setup();
    const { container } = render(<ProductTour />);
    await toOutro(user);
    const heading = screen.getByRole("heading", { name: "One real job, one honest resume." });
    expect(heading).toHaveFocus();
    expect(screen.getByText("28")).toBeInTheDocument();
    expect(screen.getByText("live jobs in her first search")).toBeInTheDocument();
    expect(screen.getByText("13¢")).toBeInTheDocument();
    expect(screen.getByText("AI cost for this resume")).toBeInTheDocument();
    expect(screen.getByText("6 of 6")).toBeInTheDocument();
    expect(screen.getByText("checks passed")).toBeInTheDocument();
    expect(screen.getByText("unverified numbers")).toBeInTheDocument();
    expect(screen.getByText(/from the run in this tour/i)).toBeInTheDocument();
    expect(screen.queryByText(/invented numbers/i)).toBeNull();
    expect(container.querySelectorAll("img")).toHaveLength(0);
    expect(document.body.innerHTML).not.toContain("rhapto.augaster.com/about");
  });

  it("token-mode deployments get Get started -> /settings and no beta/invite claim", async () => {
    sameOriginFlag.value = false;
    const user = userEvent.setup();
    render(<ProductTour />);
    await toOutro(user);
    expect(screen.getByRole("link", { name: /^get started$/i })).toHaveAttribute("href", "/settings");
    expect(screen.queryByRole("link", { name: /request access/i })).toBeNull();
    expect(screen.queryByText(/invite-only/i)).toBeNull();
    expect(screen.queryByText(/private beta/i)).toBeNull();
  });

  it("same-origin deployments get Request access -> the mailto, and say invite-only", async () => {
    sameOriginFlag.value = true;
    const user = userEvent.setup();
    render(<ProductTour />);
    await toOutro(user);
    expect(screen.getByRole("link", { name: /^request access$/i })).toHaveAttribute(
      "href",
      ACCESS_REQUEST_MAILTO,
    );
    expect(screen.queryByRole("link", { name: /get started/i })).toBeNull();
    expect(screen.getByText(/invite-only/i)).toBeInTheDocument();
    expect(screen.queryByText(/private beta/i)).toBeNull();
  });

  it("Watch again returns to step 1 and focuses its heading", async () => {
    const user = userEvent.setup();
    render(<ProductTour />);
    await toOutro(user);
    await user.click(screen.getByRole("button", { name: /watch again/i }));
    expect(title()).toHaveTextContent(STEPS[0]!.title);
    expect(title()).toHaveFocus();
  });
});

describe("ProductTour, keyboard and focus", () => {
  it("Start moves focus to the caption heading", async () => {
    const user = userEvent.setup();
    render(<ProductTour />);
    await user.click(start());
    expect(title()).toHaveFocus();
  });

  it("arrow keys work inside the tour and are ignored outside it", async () => {
    const user = userEvent.setup();
    render(<ProductTour />);
    await user.click(start());
    // Outside the tour: nothing happens.
    document.body.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true }));
    expect(title()).toHaveTextContent(STEPS[0]!.title);
    // Inside (focus is on the caption heading): moves, and the default is prevented.
    title().dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true }));
    expect(await screen.findByText(/2 of 14/)).toBeInTheDocument();
    await user.keyboard("{ArrowLeft}");
    expect(screen.getByText(/1 of 14/)).toBeInTheDocument();
  });

  it("does not react to modified arrows and does not swallow other keys", async () => {
    const user = userEvent.setup();
    render(<ProductTour />);
    await user.click(start());
    const region = screen.getByRole("region", { name: /product tour/i });
    const alt = new KeyboardEvent("keydown", { key: "ArrowRight", altKey: true, bubbles: true, cancelable: true });
    title().dispatchEvent(alt);
    expect(alt.defaultPrevented).toBe(false);
    const tab = new KeyboardEvent("keydown", { key: "Tab", bubbles: true, cancelable: true });
    title().dispatchEvent(tab);
    expect(tab.defaultPrevented).toBe(false);
    expect(within(region).getByText(/1 of 14/)).toBeInTheDocument();
  });

  it("the hotspot and Next keep focus across steps (they are not remounted)", async () => {
    const user = userEvent.setup();
    render(<ProductTour />);
    await user.click(start());
    const nextBtn = next();
    nextBtn.focus();
    await user.click(nextBtn);
    expect(next()).toBe(nextBtn);
    expect(nextBtn).toHaveFocus();
    const hot = screen.getByRole("button", { name: /^next: /i });
    hot.focus();
    await user.click(hot);
    expect(screen.getByRole("button", { name: /^next: /i })).toBe(hot);
    expect(hot).toHaveFocus();
  });
});

describe("ProductTour, motion and geometry", () => {
  it("zooms toward the hotspot when motion is allowed", async () => {
    const user = userEvent.setup();
    const { container } = render(<ProductTour />);
    await user.click(start());
    const shot = container.querySelector("img")!.parentElement as HTMLElement;
    expect(shot.style.transform).toMatch(/^translate\(-?[\d.]+%, -?[\d.]+%\) scale\(1\.25\)$/);
  });

  it("applies no transform at all under prefers-reduced-motion", async () => {
    stubMatchMedia(true);
    const user = userEvent.setup();
    const { container } = render(<ProductTour />);
    await user.click(start());
    const shot = container.querySelector("img")!.parentElement as HTMLElement;
    expect(shot.style.transform).toBe("");
    const hot = screen.getByRole("button", { name: /^next: /i });
    const plain = layout(STEPS[0]!.x, STEPS[0]!.y, 1);
    expect(hot.style.left).toBe(`${plain.hx}%`);
    expect(hot.style.top).toBe(`${plain.hy}%`);
  });

  it("positions the hotspot in percentages, and keeps it inside the frame at every step", () => {
    for (const s of STEPS) {
      expect(s.hx).toBeGreaterThan(0);
      expect(s.hx).toBeLessThan(100);
      expect(s.hy).toBeGreaterThan(0);
      expect(s.hy).toBeLessThan(100);
      expect(s.tx).toBeLessThanOrEqual(0);
      expect(s.tx).toBeGreaterThanOrEqual((1 - s.zoom) * 100);
    }
  });

  it("uses no measuring APIs and no window reads in the component source", () => {
    const src = readFileSync(
      join(dirname(fileURLToPath(import.meta.url)), "ProductTour.tsx"),
      "utf8",
    );
    const code = src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^[ \t]*\/\/.*$/gm, "");
    expect(code).not.toMatch(/ResizeObserver|getBoundingClientRect|innerWidth/);
    expect(code).toMatch(/^"use client";/);
    expect(code).not.toMatch(/#[0-9a-fA-F]{3,8}\b/);
  });
});
