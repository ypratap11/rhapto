import { act, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { renderToString } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as copy from "@/lib/coach/copy";
import { matchLabel } from "@/lib/coach/labels";
import { CoachTour } from "./CoachTour";
import { primaryCta } from "./cta";
import { TOUR_CHANGES, TOUR_FILE, TOUR_JOBS, TOUR_ROLE } from "./coachTourData";

const flag = { value: true };
vi.mock("@/lib/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/client")>();
  return {
    ...actual,
    get SAME_ORIGIN_DEPLOYMENT() {
      return flag.value;
    },
  };
});
afterEach(() => {
  flag.value = true;
});

const panels = () => screen.getAllByRole("tabpanel", { hidden: true });
const INTERACTIVE = "a, button, input, select, textarea, [role='button'], [tabindex]:not([tabindex='-1'])";
const interactiveIn = (el: Element) => el.querySelector(INTERACTIVE);

describe("CoachTour", () => {
  it("has four tabs, the first selected, and all four panels in the DOM", () => {
    render(<CoachTour />);
    const tabs = screen.getAllByRole("tab");
    expect(tabs.map((t) => t.textContent)).toEqual(["1 Upload", "2 Role", "3 Top matches", "4 Your resume"]);
    expect(tabs[0]).toHaveAttribute("aria-selected", "true");
    expect(panels()).toHaveLength(4); // server-rendered: inactive panels are hidden, not absent
    expect(screen.getByRole("heading", { level: 2, name: "See the coach, step by step" })).toBeInTheDocument();
  });

  it("each panel carries a visible keyboard focus ring (the shared TabsContent removes the outline)", () => {
    render(<CoachTour />);
    for (const panel of panels()) expect(panel.className).toContain("focus-visible:ring");
  });

  it("is a section with the #tour anchor and room under the sticky bar", () => {
    const { container } = render(<CoachTour />);
    const section = container.querySelector("section#tour")!;
    expect(section.className).toContain("scroll-mt-20");
    expect(section).toHaveAttribute("aria-labelledby");
  });

  it("keeps the tabs on one scrollable row on phones: no wrap, no visible scrollbar, 44px targets", () => {
    render(<CoachTour />);
    const cls = screen.getByRole("tablist").className;
    expect(cls).not.toContain("flex-wrap");
    for (const c of ["flex-nowrap", "overflow-x-auto", "justify-start", "sm:justify-center", "[scrollbar-width:none]", "group-data-horizontal/tabs:h-auto"]) expect(cls).toContain(c);
    expect(screen.getAllByRole("tab")[0]!.className).toContain("max-sm:min-h-11");
  });

  it("moves selection by click and by arrow keys, wrapping, Home and End", async () => {
    const user = userEvent.setup();
    render(<CoachTour />);
    const tabs = () => screen.getAllByRole("tab");
    await user.click(tabs()[2]!);
    expect(tabs()[2]).toHaveAttribute("aria-selected", "true");
    await user.keyboard("{ArrowRight}");
    expect(tabs()[3]).toHaveAttribute("aria-selected", "true");
    await user.keyboard("{ArrowRight}");
    expect(tabs()[0]).toHaveAttribute("aria-selected", "true"); // wraps
    await user.keyboard("{ArrowLeft}");
    expect(tabs()[3]).toHaveAttribute("aria-selected", "true"); // wraps back
    await user.keyboard("{Home}");
    expect(tabs()[0]).toHaveAttribute("aria-selected", "true");
    await user.keyboard("{End}");
    expect(tabs()[3]).toHaveAttribute("aria-selected", "true");
  });

  it("always shows the fictional-data line", async () => {
    const user = userEvent.setup();
    render(<CoachTour />);
    expect(screen.getByText("Example with a fictional person, Maya Chen.")).toBeInTheDocument();
    await user.click(screen.getAllByRole("tab")[3]!);
    expect(screen.getByText("Example with a fictional person, Maya Chen.")).toBeInTheDocument();
  });

  it("shows no interactive element inside any panel", () => {
    render(<CoachTour />);
    for (const panel of panels()) expect(interactiveIn(panel)).toBeNull();
  });

  it("the inert-panel check FAILS on a fixture panel containing a link", () => {
    render(<div role="tabpanel"><a href="/x">x</a></div>);
    expect(interactiveIn(screen.getByRole("tabpanel"))).not.toBeNull(); // same helper as the real check, so it proves that check can fail
  });

  it("the interactive elements of the window are the four tabs and the CTA links only", () => {
    const { container } = render(<CoachTour />);
    const outside = [...container.querySelectorAll("a, button")].filter((el) => el.getAttribute("role") !== "tab");
    expect(outside.length).toBeGreaterThan(0);
    for (const el of outside) expect(el.closest("[role='tabpanel']")).toBeNull();
  });

  it("panels show only coach strings from lib/coach/copy plus the fictional data (drift guard)", () => {
    render(<CoachTour />);
    const fictional = [
      TOUR_FILE,
      TOUR_ROLE,
      ...TOUR_JOBS.flatMap((j) => [j.title, j.company, matchLabel(j.fit, j.minFit)]),
      ...TOUR_CHANGES.flatMap((c) => [c.reason, c.after]),
    ];
    const known = [
      copy.UPLOAD_TITLE, copy.UPLOAD_HINT, copy.CHOOSE_FILE,
      copy.roleQuestion(TOUR_ROLE), copy.ROLE_YES, copy.ROLE_OTHER,
      copy.matchesTitle(TOUR_ROLE), copy.TAILOR_THIS,
      copy.RESULT_TITLE, copy.RESULT_READY, copy.DOWNLOAD_DOCX, copy.DOWNLOAD_PDF, copy.WHAT_CHANGED,
    ];
    for (const panel of panels()) {
      let left = panel.textContent ?? "";
      for (const s of [...known, ...fictional].sort((a, b) => b.length - a.length)) left = left.split(s).join("");
      expect(left.trim(), "text in a panel that the coach does not show").toBe("");
    }
    // and nothing from the old invented copy
    expect(document.body.textContent).not.toMatch(/Read 3 roles|We think you are aiming/);
  });

  it("panel 1 is title, hint and the file chip only: no transcript line", () => {
    render(<CoachTour />);
    const first = panels()[0]!;
    expect(first.textContent).toContain(copy.UPLOAD_TITLE);
    expect(first.textContent).toContain(copy.UPLOAD_HINT);
    expect(first.textContent).toContain("maya-chen-resume.docx");
    expect(first.textContent).not.toMatch(/Resume:/);
  });

  it("draws match labels as the coach does: Strong, Strong, Good, with the three fictional companies", () => {
    render(<CoachTour />);
    const third = panels()[2]!;
    expect(within(third).getAllByText("Strong match")).toHaveLength(2);
    expect(within(third).getAllByText("Good match")).toHaveLength(1);
    for (const c of ["Contoso Robotics", "Fabrikam Health", "Tailspin Air"]) expect(third.textContent).toContain(c);
  });

  it("hosted: 'Try it with your resume' matches the primary CTA; there is no request-access link or 'No invite yet?' under the tour", () => {
    render(<CoachTour />);
    expect(screen.getByRole("link", { name: /Try it with your resume/ })).toHaveAttribute("href", primaryCta(true).href);
    expect(screen.queryByRole("link", { name: /request beta access/i })).toBeNull();
    expect(screen.queryByText(/No invite yet\?/)).toBeNull();
  });

  it("token mode: goes to /settings and shows neither /start nor a request link", () => {
    flag.value = false;
    const { container } = render(<CoachTour />);
    expect(screen.getByRole("link", { name: /Try it with your resume/ })).toHaveAttribute("href", "/settings");
    expect(screen.queryByRole("link", { name: /request beta access/i })).toBeNull();
    expect(container.querySelector("a[href='/start']")).toBeNull();
  });
});

describe("CoachTour autoplay", () => {
  type Cb = (entries: { isIntersecting: boolean }[]) => void;
  let observed: { cb: Cb } | null;
  const setMedia = (reduce: boolean) =>
    Object.defineProperty(window, "matchMedia", {
      configurable: true,
      writable: true,
      value: (q: string) => ({ matches: reduce, media: q, addEventListener() {}, removeEventListener() {} }),
    });
  const selected = () => screen.getAllByRole("tab").findIndex((t) => t.getAttribute("aria-selected") === "true");
  const advance = (ms: number) => act(() => void vi.advanceTimersByTime(ms));
  const stage = () => screen.getByTestId("tour-stage");
  const scrollIntoView = vi.fn();

  beforeEach(() => {
    vi.useFakeTimers();
    // Testing Library drains microtasks after each user-event call with a setTimeout; it only advances fake
    // timers for that wait when a `jest` global exists, so under vitest it would hang. Give it the shim.
    vi.stubGlobal("jest", { advanceTimersByTime: (ms: number) => vi.advanceTimersByTime(ms) });
    observed = null;
    setMedia(false);
    Element.prototype.scrollIntoView = scrollIntoView;
    scrollIntoView.mockClear();
    Object.defineProperty(window, "IntersectionObserver", {
      configurable: true,
      writable: true,
      value: class {
        constructor(cb: Cb) {
          observed = { cb };
        }
        observe() {}
        unobserve() {}
        disconnect() {}
      },
    });
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    Reflect.deleteProperty(window, "matchMedia");
    Reflect.deleteProperty(window, "IntersectionObserver");
    Reflect.deleteProperty(Element.prototype, "scrollIntoView");
  });

  it("advances 1->2->3->4->1 every 4 s", () => {
    render(<CoachTour />);
    expect(selected()).toBe(0);
    advance(3999);
    expect(selected()).toBe(0);
    advance(1);
    expect(selected()).toBe(1);
    advance(4000);
    expect(selected()).toBe(2);
    advance(4000);
    expect(selected()).toBe(3);
    advance(4000);
    expect(selected()).toBe(0); // wraps
  });

  it("shows a progress bar only on the active tab while running (one clock with the timer)", () => {
    render(<CoachTour />);
    expect(screen.getAllByRole("tab")[0]!.querySelector("[data-tour-progress]")).not.toBeNull();
    expect(screen.getAllByRole("tab")[1]!.querySelector("[data-tour-progress]")).toBeNull();
    advance(4000);
    expect(screen.getAllByRole("tab")[1]!.querySelector("[data-tour-progress]")).not.toBeNull();
    expect(document.querySelector("[data-tour-progress]")!.getAttribute("aria-hidden")).toBe("true");
  });

  it("pauses while the pointer is over the stage and resumes with a fresh 4 s on leave", () => {
    render(<CoachTour />);
    fireEvent.pointerEnter(stage());
    advance(20000);
    expect(selected()).toBe(0);
    expect(document.querySelector("[data-tour-progress]")).toBeNull();
    fireEvent.pointerLeave(stage());
    advance(3999);
    expect(selected()).toBe(0);
    advance(1);
    expect(selected()).toBe(1);
  });

  it("pauses while focus is inside the stage and resumes on blur", () => {
    render(<CoachTour />);
    const first = screen.getAllByRole("tab")[0]!;
    act(() => first.focus());
    advance(20000);
    expect(selected()).toBe(0);
    act(() => first.blur());
    advance(4000);
    expect(selected()).toBe(1);
  });

  it("pauses while the tour is not in the viewport and resumes when it returns", () => {
    render(<CoachTour />);
    act(() => observed!.cb([{ isIntersecting: false }]));
    advance(20000);
    expect(selected()).toBe(0);
    act(() => observed!.cb([{ isIntersecting: true }]));
    advance(4000);
    expect(selected()).toBe(1);
  });

  it("a tab click selects it and stops autoplay for the rest of the visit", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<CoachTour />);
    await user.click(screen.getAllByRole("tab")[2]!);
    expect(selected()).toBe(2);
    advance(60000);
    expect(selected()).toBe(2);
    expect(screen.getByRole("button", { name: "Play demo" })).toBeInTheDocument();
  });

  it("clicking the already-active tab also stops autoplay (M-4)", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<CoachTour />);
    await user.click(screen.getAllByRole("tab")[0]!);
    expect(selected()).toBe(0);
    act(() => screen.getAllByRole("tab")[0]!.blur());
    fireEvent.pointerLeave(stage());
    advance(60000);
    expect(selected()).toBe(0);
    expect(screen.getByRole("button", { name: "Play demo" })).toBeInTheDocument();
  });

  it("an arrow key also takes over", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<CoachTour />);
    act(() => screen.getAllByRole("tab")[0]!.focus());
    await user.keyboard("{ArrowRight}");
    expect(selected()).toBe(1);
    act(() => screen.getAllByRole("tab")[1]!.blur());
    advance(60000);
    expect(selected()).toBe(1);
  });

  it("the pause button stops autoplay, flips its label, and Play restarts from a fresh 4 s", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<CoachTour />);
    await user.click(screen.getByRole("button", { name: "Pause demo" }));
    expect(screen.queryByRole("button", { name: "Pause demo" })).toBeNull();
    advance(20000);
    expect(selected()).toBe(0);
    await user.click(screen.getByRole("button", { name: "Play demo" }));
    expect(screen.getByRole("button", { name: "Pause demo" })).toBeInTheDocument();
    advance(4000);
    expect(selected()).toBe(1);
  });

  it("Play works while the button is focused and hovered: the bar is outside the hold zone (architect I2)", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<CoachTour />);
    await user.click(screen.getByRole("button", { name: "Pause demo" }));
    const play = screen.getByRole("button", { name: "Play demo" });
    expect(stage().contains(play)).toBe(false);
    await user.click(play); // leaves pointer and focus on the button
    expect(document.activeElement).toBe(play);
    advance(4000);
    expect(selected()).toBe(1);
  });

  it("prefers-reduced-motion: no autoplay and no progress bar; Play still starts it", async () => {
    setMedia(true);
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<CoachTour />);
    advance(30000);
    expect(selected()).toBe(0);
    expect(document.querySelector("[data-tour-progress]")).toBeNull();
    await user.click(screen.getByRole("button", { name: "Play demo" }));
    advance(4000);
    expect(selected()).toBe(1);
    expect(document.querySelector("[data-tour-progress]")).toBeNull();
  });

  it("does not announce changes, move focus, or scroll the page: no live region, activeElement stable, scrollIntoView never called", () => {
    const { container } = render(<CoachTour />);
    expect(container.querySelector("[aria-live], [role='status'], [role='alert']")).toBeNull();
    const before = document.activeElement;
    advance(16000);
    expect(document.activeElement).toBe(before);
    expect(scrollIntoView).not.toHaveBeenCalled();
  });

  it("keeps the active phone tab in view by moving the tablist's own scrollLeft", () => {
    render(<CoachTour />);
    const list = screen.getByRole("tablist");
    const set = vi.fn();
    Object.defineProperty(list, "scrollLeft", { configurable: true, get: () => 0, set });
    advance(4000);
    expect(set).toHaveBeenCalled();
    expect(scrollIntoView).not.toHaveBeenCalled();
  });

  it("is hydration-safe: the server HTML is tab 1, not playing, with no progress bar", () => {
    const html = renderToString(<CoachTour />);
    expect(html).toContain('aria-label="Play demo"');
    expect(html).not.toContain("data-tour-progress");
    expect(html).not.toContain("Pause demo");
    expect(html.match(/<button[^>]*role="tab"[^>]*>/)![0]).toContain('aria-selected="true"');
  });

  it("window bar: 'Live demo' chip, a pause button outside every panel, 44px phone target", () => {
    render(<CoachTour />);
    expect(screen.getByText("Live demo")).toBeInTheDocument();
    for (const panel of panels()) expect(panel.querySelector("button")).toBeNull();
    expect(screen.getByRole("button", { name: /demo$/ }).className).toContain("max-sm:size-11");
  });

  it("panels sit in one fixed min-height wrapper; panel 3 rows and panel 4's changed line carry the motion hooks", () => {
    const { container } = render(<CoachTour />);
    expect(container.querySelector("[data-tour-panels]")!.className).toMatch(/min-h-\[/);
    for (const panel of panels()) expect(panel.className).toContain("tour-panel");
    expect(panels()[2]!.querySelectorAll(".tour-row")).toHaveLength(3);
    expect(panels()[3]!.querySelectorAll(".tour-hl")).toHaveLength(1);
  });

  it("all tour animation rules live inside a prefers-reduced-motion: no-preference block", () => {
    const css = readFileSync(join(import.meta.dirname, "..", "..", "app", "globals.css"), "utf8");
    const marker = css.indexOf("/* tour motion */");
    expect(marker).toBeGreaterThan(-1);
    const media = css.indexOf("@media (prefers-reduced-motion: no-preference)", marker);
    expect(media).toBeGreaterThan(marker);
    const block = css.slice(media);
    for (const sel of [".tour-panel:not([hidden])", ".tour-row", "animation: tour-hl", ".tour-progress"]) expect(block, sel).toContain(sel);
    // nothing outside the block starts an animation on these classes
    expect(css.slice(marker, media)).not.toMatch(/\.tour-(panel|row|progress)[^{]*\{[^}]*animation/);
  });
});
