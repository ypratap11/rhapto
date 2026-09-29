import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CaughtDemo } from "./CaughtDemo";

// The three messages and paths below are typed out, not imported from the component: they are the
// strings `apps/api/src/rhapto/engine/guardrails/{metrics,entities,provenance}.py` produce, and a
// test that read them back from the component would agree with any typo. This file is the only
// web-side link to the API wording; the .py files carry a comment pointing here.
const EXPECTED = [
  {
    button: /unverified number/i,
    rule: "no-unverified-metrics",
    path: "sections[0].entries[1].bullets[1]",
    message: "block 'acme-forecast' is not verified but the text contains metric(s): 42%",
  },
  {
    button: /invented job title/i,
    rule: "no-invented-entities",
    path: "sections[0].entries[0]",
    message:
      "role 'Director of Data Platform' does not match block 'northwind-onboarding' ('Data Platform Lead')",
  },
  {
    button: /unsourced line/i,
    rule: "provenance",
    path: "sections[0].entries[0]",
    message: "source block 'acme-board' does not exist",
  },
] as const;

function stubMatchMedia(reduce: boolean) {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: reduce && query.includes("prefers-reduced-motion"),
    media: query,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  })) as unknown as typeof window.matchMedia;
}

function pressed(): string[] {
  return screen
    .getAllByRole("button")
    .filter((b) => b.getAttribute("aria-pressed") === "true")
    .map((b) => b.textContent ?? "");
}

function setHidden(value: boolean) {
  Object.defineProperty(document, "hidden", { value, configurable: true });
}

beforeEach(() => {
  vi.useFakeTimers();
  stubMatchMedia(false);
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  // jsdom has no matchMedia; remove the stub so tests stay independent
  Reflect.deleteProperty(window, "matchMedia");
  setHidden(false);
});

describe("CaughtDemo, at rest", () => {
  it("renders a complete caught case on the first frame, before any effect or timer runs", () => {
    render(<CaughtDemo />);
    expect(screen.getByText(EXPECTED[0].message)).toBeInTheDocument();
    expect(screen.getByText(EXPECTED[0].rule)).toBeInTheDocument();
    expect(screen.getByText(EXPECTED[0].path)).toBeInTheDocument();
    expect(
      screen.getByText(/Increased forecast accuracy by 42% using a new ML model\./),
    ).toBeInTheDocument();
    expect(pressed()).toHaveLength(1);
  });

  it("is a button group with exactly one aria-pressed=true, and three real buttons", () => {
    render(<CaughtDemo />);
    const group = screen.getByRole("group");
    expect(group).toHaveAccessibleName();
    const buttons = within(group).getAllByRole("button");
    expect(buttons).toHaveLength(3);
    for (const b of buttons) expect(b).toHaveAttribute("aria-pressed");
    expect(pressed()).toHaveLength(1);
    expect(buttons[0]).toHaveAttribute("aria-pressed", "true");
  });

  it("hides the stamp from assistive tech, and says the draft was rejected in text", () => {
    render(<CaughtDemo />);
    const stamp = screen.getByTestId("caught-stamp");
    expect(stamp).toHaveAttribute("aria-hidden", "true");
    expect(stamp).toHaveTextContent(/caught/i);
    // line-through is invisible to a screen reader; without this prefix the fabricated sentence is
    // read out as plain prose.
    expect(screen.getByText(/Rejected draft:/)).toBeInTheDocument();
  });

  it("keeps the live region present and empty until the visitor clicks", () => {
    render(<CaughtDemo />);
    const status = screen.getByRole("status");
    expect(status).toBeEmptyDOMElement();
    // and the visible report is not inside it, or every auto-advance would be announced
    expect(status).not.toContainElement(screen.getByText(EXPECTED[0].message));
  });

  it("puts the stamp's motion in CSS behind motion-safe, resting fully visible", () => {
    render(<CaughtDemo />);
    const cls = screen.getByTestId("caught-stamp").className;
    expect(cls).toMatch(/motion-safe:animate-in/);
    // no un-animated state hides it: nothing at rest may be transparent or invisible
    expect(cls).not.toMatch(/(^|\s)(opacity-0|invisible|hidden)(\s|$)/);
  });
});

describe("CaughtDemo, the three cases", () => {
  it.each(EXPECTED.map((c, i) => [i, c] as const))(
    "case %i shows its rule, path and message exactly as the guardrail produces them",
    (_i, c) => {
      render(<CaughtDemo />);
      fireEvent.click(screen.getByRole("button", { name: c.button }));
      expect(screen.getByText(c.rule)).toBeInTheDocument();
      expect(screen.getByText(c.path)).toBeInTheDocument();
      expect(screen.getByText(c.message)).toBeInTheDocument();
      expect(screen.getByRole("button", { name: c.button })).toHaveAttribute(
        "aria-pressed",
        "true",
      );
      expect(pressed()).toHaveLength(1);
      // announced, and only because the visitor asked
      expect(screen.getByRole("status")).toHaveTextContent(c.rule);
    },
  );

  it("replays the stamp on a case change by remounting it, not by toggling a class", () => {
    render(<CaughtDemo />);
    const before = screen.getByTestId("caught-stamp");
    fireEvent.click(screen.getByRole("button", { name: EXPECTED[1].button }));
    expect(screen.getByTestId("caught-stamp")).not.toBe(before);
  });

  it("makes each path countable in its own fragment", () => {
    render(<CaughtDemo />);
    // entries[1].bullets[1]: two entries, the second with a real first bullet and then the draft
    let entries = screen.getAllByTestId("entry");
    expect(entries).toHaveLength(2);
    expect(within(entries[1]!).getAllByTestId("bullet")).toHaveLength(2);

    for (const c of [EXPECTED[1], EXPECTED[2]]) {
      fireEvent.click(screen.getByRole("button", { name: c.button }));
      // entries[0]: the fragment is exactly one entry
      entries = screen.getAllByTestId("entry");
      expect(entries).toHaveLength(1);
    }
  });

  it("cites a real block id in the line sent instead", () => {
    render(<CaughtDemo />);
    fireEvent.click(screen.getByRole("button", { name: EXPECTED[2].button }));
    expect(screen.getByText(/block: acme-migration/)).toBeInTheDocument();
  });

  it("says what is true about each check: metrics and provenance always run, entities is on by default", () => {
    render(<CaughtDemo />);
    expect(screen.getByText(/always runs/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: EXPECTED[1].button }));
    expect(screen.getByText(/on by default/i)).toBeInTheDocument();
    expect(screen.queryByText(/always runs/i)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: EXPECTED[2].button }));
    expect(screen.getByText(/always runs/i)).toBeInTheDocument();
  });

  it("presents this as inside a run, and never as something the user is shown every time", () => {
    const { container } = render(<CaughtDemo />);
    const text = container.textContent ?? "";
    expect(text).toMatch(/inside a run/i);
    expect(text).toMatch(/one fix/i);
    expect(text).toMatch(/blocked/i);
    expect(text).not.toMatch(/no document|not produced|never produced|before this document/i);
  });
});

describe("CaughtDemo, auto-advance", () => {
  it("advances every 6 seconds, without announcing", () => {
    render(<CaughtDemo />);
    act(() => void vi.advanceTimersByTime(6000));
    expect(screen.getByText(EXPECTED[1].message)).toBeInTheDocument();
    act(() => void vi.advanceTimersByTime(6000));
    expect(screen.getByText(EXPECTED[2].message)).toBeInTheDocument();
    act(() => void vi.advanceTimersByTime(6000));
    expect(screen.getByText(EXPECTED[0].message)).toBeInTheDocument();
    expect(screen.getByRole("status")).toBeEmptyDOMElement();
  });

  it.each([
    ["pointerenter", (el: HTMLElement) => fireEvent.pointerEnter(el)],
    ["focusin", (el: HTMLElement) => fireEvent.focusIn(el)],
    ["click", (el: HTMLElement) => fireEvent.click(el)],
  ])("pauses for good on %s", (_name, interact) => {
    render(<CaughtDemo />);
    interact(screen.getByRole("group"));
    const shown = screen.getByRole("button", { pressed: true }).textContent;
    act(() => void vi.advanceTimersByTime(60000));
    expect(screen.getByRole("button", { pressed: true }).textContent).toBe(shown);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("does not advance while the tab is hidden, and resumes when it is visible again", () => {
    render(<CaughtDemo />);
    setHidden(true);
    act(() => void vi.advanceTimersByTime(30000));
    expect(screen.getByText(EXPECTED[0].message)).toBeInTheDocument();
    setHidden(false);
    act(() => void vi.advanceTimersByTime(6000));
    expect(screen.getByText(EXPECTED[1].message)).toBeInTheDocument();
  });

  it("schedules no timer at all under prefers-reduced-motion", () => {
    stubMatchMedia(true);
    const spy = vi.spyOn(globalThis, "setInterval");
    render(<CaughtDemo />);
    expect(spy).not.toHaveBeenCalled();
    expect(vi.getTimerCount()).toBe(0);
    act(() => void vi.advanceTimersByTime(60000));
    expect(screen.getByText(EXPECTED[0].message)).toBeInTheDocument();
  });

  it("still renders when matchMedia is absent", () => {
    Reflect.deleteProperty(window, "matchMedia");
    render(<CaughtDemo />);
    expect(screen.getByText(EXPECTED[0].message)).toBeInTheDocument();
  });

  it("clears its timer on unmount", () => {
    const { unmount } = render(<CaughtDemo />);
    expect(vi.getTimerCount()).toBe(1);
    unmount();
    expect(vi.getTimerCount()).toBe(0);
  });
});
