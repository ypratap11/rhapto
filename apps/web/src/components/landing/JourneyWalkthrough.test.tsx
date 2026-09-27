import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { JourneyWalkthrough } from "./JourneyWalkthrough";

// jsdom implements neither `IntersectionObserver` nor a settable `prefers-reduced-motion`, and the
// shared `vitest.setup.ts` is outside this surface, so both are stubbed per file here. The stub keeps
// every constructed observer's callback so a test can decide exactly when the walkthrough comes into
// view -- which is the trigger the component is built around, and the thing that must not fire early.
const observerCallbacks: Array<(entries: Array<{ isIntersecting: boolean }>) => void> = [];

class FakeIntersectionObserver {
  constructor(private readonly callback: (entries: Array<{ isIntersecting: boolean }>) => void) {
    observerCallbacks.push(callback);
  }
  observe() {}
  unobserve() {}
  disconnect() {}
}

/** Nothing has scrolled into view yet unless a test says so. */
function scrollIntoView() {
  act(() => {
    for (const callback of observerCallbacks) callback([{ isIntersecting: true }]);
  });
}

function stubReducedMotion(reduce: boolean) {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: reduce && query.includes("prefers-reduced-motion"),
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  }));
}

const BEAT_MS = 950;
const TITLES = [
  "You ask for access",
  "You bring your resume",
  "You pick a track",
  "Jobs arrive and get scored",
  "Rhapto tailors one",
  "You review and send it",
] as const;

function beatStates() {
  return screen.getAllByRole("listitem").map((li) => li.dataset.beat);
}

function currentBeat() {
  return screen.queryByRole("button", { current: "step" });
}

/** Every class in a beat's subtree that would make it invisible or hard to read.
 *
 * This is the one place a class name is asserted on, and deliberately: the invariant is "a beat that
 * has not arrived is muted, never faded and never hidden", and there is no semantic signal for it.
 * jsdom loads no CSS, so `toBeVisible()` alone cannot see a Tailwind `opacity-0` -- it only catches
 * inline styles and the `hidden` attribute. Both checks run: the class sweep for the utility classes,
 * `toBeVisible()` for everything else. `opacity-100` deliberately does not match.
 *
 * What it protects: an un-arrived beat sits at that state for the whole time a reader is stepping
 * backwards through the journey, so faded text would put --muted-foreground below AA on the mint
 * band, and an opacity-0 button is still focusable and still clickable.
 */
function hidingClasses(root: Element) {
  return [root, ...root.querySelectorAll("*")]
    .flatMap((node) => Array.from(node.classList))
    .filter((name) => /^(opacity-\d{1,2}|invisible|hidden|sr-only)$/.test(name));
}

beforeEach(() => {
  observerCallbacks.length = 0;
  vi.stubGlobal("IntersectionObserver", FakeIntersectionObserver);
  stubReducedMotion(false);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("JourneyWalkthrough", () => {
  it("names all six beats, in the owner's order, starting at asking for access and ending on the human send", () => {
    render(<JourneyWalkthrough />);
    const beats = screen.getAllByRole("listitem");
    expect(beats.map((li) => li.querySelector("button")?.firstElementChild?.textContent)).toEqual([
      ...TITLES,
    ]);
    // Beat 6 is the product's first non-negotiable rule, which is why the journey ends here rather
    // than on a finished document. Losing it would make this an "it applies for you" animation.
    expect(beats[5]).toHaveTextContent(/nothing in it sends an application for you/i);
  });

  it("holds still until it has been scrolled into view, then plays the beats in order and rests on the last", () => {
    vi.useFakeTimers();
    render(<JourneyWalkthrough />);

    // Nothing has played: no beat is current and every beat is pending.
    expect(currentBeat()).toBeNull();
    expect(beatStates()).toEqual(Array(6).fill("pending"));

    // And a pending beat is readable, not faded out and not hidden -- the last one especially,
    // since it carries the never-submits promise and is pending for the whole run.
    for (const beat of screen.getAllByRole("listitem")) {
      expect(beat.querySelector("button")).toBeVisible();
      expect(hidingClasses(beat)).toEqual([]);
    }

    scrollIntoView();
    expect(currentBeat()).toHaveTextContent(TITLES[0]);
    expect(beatStates()).toEqual(["arrived", ...Array(5).fill("pending")]);

    for (const title of TITLES.slice(1)) {
      act(() => void vi.advanceTimersByTime(BEAT_MS));
      expect(currentBeat()).toHaveTextContent(title);
    }
    expect(beatStates()).toEqual(Array(6).fill("arrived"));

    // Plays ONCE and rests: another five beats' worth of time must not wrap back to beat 1.
    act(() => void vi.advanceTimersByTime(BEAT_MS * 5));
    expect(currentBeat()).toHaveTextContent(TITLES[5]);
    expect(beatStates()).toEqual(Array(6).fill("arrived"));
  });

  it("lets a reader jump to a single beat, and that takes the run over rather than being overwritten by it", () => {
    vi.useFakeTimers();
    render(<JourneyWalkthrough />);
    scrollIntoView();

    const third = screen.getByRole("button", { name: new RegExp(TITLES[2], "i") });
    act(() => third.click());
    expect(third).toHaveAttribute("aria-current", "step");
    expect(beatStates()).toEqual([...Array(3).fill("arrived"), ...Array(3).fill("pending")]);

    // The autoplay was mid-run when the reader reached in. If it were still ticking it would move
    // off this beat a moment later.
    act(() => void vi.advanceTimersByTime(BEAT_MS * 4));
    expect(third).toHaveAttribute("aria-current", "step");
    expect(beatStates()).toEqual([...Array(3).fill("arrived"), ...Array(3).fill("pending")]);
  });

  it("replays from the first beat on demand, after the run has finished", () => {
    vi.useFakeTimers();
    render(<JourneyWalkthrough />);
    scrollIntoView();
    act(() => void vi.advanceTimersByTime(BEAT_MS * 6));
    expect(currentBeat()).toHaveTextContent(TITLES[5]);

    act(() => screen.getByRole("button", { name: /replay/i }).click());
    expect(currentBeat()).toHaveTextContent(TITLES[0]);
    expect(beatStates()).toEqual(["arrived", ...Array(5).fill("pending")]);

    act(() => void vi.advanceTimersByTime(BEAT_MS));
    expect(currentBeat()).toHaveTextContent(TITLES[1]);
  });

  it("honours prefers-reduced-motion: no run at all, all six beats in their final state, controls still working", () => {
    stubReducedMotion(true);
    vi.useFakeTimers();
    render(<JourneyWalkthrough />);
    scrollIntoView();

    // Final state immediately, with no elapsed time: there is nothing to watch move.
    expect(beatStates()).toEqual(Array(6).fill("arrived"));
    expect(currentBeat()).toHaveTextContent(TITLES[5]);

    // And no timer was armed, so nothing walks backwards or forwards afterwards.
    act(() => void vi.advanceTimersByTime(BEAT_MS * 6));
    expect(beatStates()).toEqual(Array(6).fill("arrived"));
    expect(currentBeat()).toHaveTextContent(TITLES[5]);

    // Controls still do their job: stepping still selects one beat, and replay returns to the
    // finished state rather than starting an animation.
    const second = screen.getByRole("button", { name: new RegExp(TITLES[1], "i") });
    act(() => second.click());
    expect(second).toHaveAttribute("aria-current", "step");
    act(() => screen.getByRole("button", { name: /replay/i }).click());
    expect(beatStates()).toEqual(Array(6).fill("arrived"));
  });

  it("is keyboard-operable: Tab reaches the replay control and then the beats, and Enter activates them", async () => {
    // Real timers and no intersection, so nothing is playing and focus order is the only thing moving.
    render(<JourneyWalkthrough />);
    const user = userEvent.setup();

    // Really press Tab rather than calling .focus(): .focus() passes on an element Tab can never
    // land on, which is exactly how a div-with-onclick would slip through here.
    await user.tab();
    expect(screen.getByRole("button", { name: /replay/i })).toHaveFocus();

    await user.tab();
    const first = screen.getByRole("button", { name: new RegExp(TITLES[0], "i") });
    expect(first).toHaveFocus();

    await user.keyboard("{Enter}");
    expect(first).toHaveAttribute("aria-current", "step");
    expect(beatStates()).toEqual(["arrived", ...Array(5).fill("pending")]);
  });

  it("shows the finished journey when there is no IntersectionObserver to tell it the reader arrived", () => {
    vi.stubGlobal("IntersectionObserver", undefined);
    render(<JourneyWalkthrough />);
    expect(beatStates()).toEqual(Array(6).fill("arrived"));
  });

  it("beat 2 says what main actually does: paragraphs labelled, blocks proposed, nothing saved until you accept", () => {
    // This test previously asserted the opposite -- that a .docx is only "edited in place" -- on the
    // false premise that resume-to-blocks import was an unmerged branch. It is on `main`
    // (`engine/import_resume.py`, `POST /api/v1/profile/import-resume`, reachable from Settings), so
    // the old wording hid a shipped feature and this test defended the hiding. The proposal/review
    // half is asserted too: writing "Rhapto turns your resume into blocks" with no mention that you
    // accept them first would swap one overstatement for another.
    render(<JourneyWalkthrough />);
    const resumeBeat = screen.getAllByRole("listitem")[1];
    expect(resumeBeat).toHaveTextContent(/labels every paragraph/i);
    expect(resumeBeat).toHaveTextContent(/offers you a library of blocks drawn from it/i);
    expect(resumeBeat).toHaveTextContent(/nothing is saved until you accept it/i);
  });

  it("beat 5 states the guardrail promise the engine actually keeps, in both tailoring modes", () => {
    render(<JourneyWalkthrough />);
    const tailorBeat = screen.getAllByRole("listitem")[4]!;
    // Provenance really is a hard stop in both modes (blocks: OrphanBulletError -> docx = b"";
    // tune: nothing written unless the report passes).
    expect(tailorBeat).toHaveTextContent(/stops the file being produced at all/i);
    // An unverified metric is NOT. Blocks mode renders and persists the DOCX with the number in it,
    // marks the package blocked, and 409s mark-ready -- pinned in apps/api's own
    // tests/unit/test_pipeline.py. "Never reaches the file" shipped here and was false; this is the
    // assertion that stops it coming back.
    expect(tailorBeat).toHaveTextContent(/marks the whole package blocked and keeps it from being marked ready/i);
    expect(tailorBeat.textContent ?? "").not.toMatch(/never reaches the file|never (gets|makes it) into/i);
    // And the tune-mode half of "one click drafts" is the reviewed card wording, not "keeping your
    // own wording" -- tune mode rewrites whole paragraphs, it does not preserve them.
    expect(tailorBeat).toHaveTextContent(/rather than writing over it/i);
    expect(tailorBeat.textContent ?? "").not.toMatch(/keeping your own wording/i);
  });

  it("beat 1 does not tell a self-hoster they are already signed in", () => {
    // TokenGate makes only /, /settings and /about public and asks for the API URL and bearer token
    // before anything else renders, which is why this page's self-hosted CTA is "Get started" ->
    // /settings. "You are already in" would repeat, in the other deployment, the exact defect this
    // change exists to fix.
    render(<JourneyWalkthrough />);
    const firstBeat = screen.getAllByRole("listitem")[0]!;
    expect(firstBeat).toHaveTextContent(/there is nobody to ask: you point Rhapto at your own instance/i);
    expect(firstBeat.textContent ?? "").not.toMatch(/already in\b/i);
  });

  it("names job aggregators as well as company boards, the way the rest of the page does", () => {
    // main registers four board pollers and seven aggregators
    // (services/discovery/sources/__init__.py). Saying only "company boards" understated it.
    render(<JourneyWalkthrough />);
    expect(screen.getAllByRole("listitem")[3]).toHaveTextContent(/company boards and job aggregators/i);
  });
});
