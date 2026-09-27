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

  it("describes only what main does: a .docx is edited in place, not turned into blocks by itself", () => {
    // `resume-import` is unmerged. Promising automatic resume-to-blocks extraction here would make
    // this walkthrough the one thing on the page that overstates Rhapto.
    render(<JourneyWalkthrough />);
    const resumeBeat = screen.getAllByRole("listitem")[1];
    expect(resumeBeat).toHaveTextContent(/edits that document in place/i);
    expect(resumeBeat).toHaveTextContent(/write a library of blocks/i);
  });
});
