"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { usePrefersReducedMotion } from "@/lib/motion";

/** One slide every 4 s. The progress bar's CSS duration is set from this same constant. */
export const TOUR_INTERVAL_MS = 4000;

/** Self-playing tour state. Autoplay is held (not cancelled) while the pointer or focus is in the stage or
 * while the tour is off-screen; a user tab selection turns it off; the play button turns it on, even under
 * reduced motion. running = playing && !userTookOver && !hovered && !focusWithin && inView && !reducedMotion,
 * with `choice` folding playing / userTookOver / the reduced-motion override into one value. */
export function useTourAutoplay<T extends string>(values: readonly T[]) {
  const [value, setValue] = useState<T>(values[0] as T);
  // null: the visitor has not chosen, follow the system preference. "off": they picked a tab or pressed
  // Pause. "on": they pressed Play.
  const [choice, setChoice] = useState<"on" | "off" | null>(null);
  const [hover, setHover] = useState(false);
  const [focus, setFocus] = useState(false);
  const [inView, setInView] = useState(true);
  const sectionRef = useRef<HTMLElement | null>(null);
  const reduced = usePrefersReducedMotion();

  const playing = choice === null ? !reduced : choice === "on";
  const running = playing && !hover && !focus && inView;

  useEffect(() => {
    if (!running) return;
    const id = window.setTimeout(() => {
      setValue((cur) => values[(values.indexOf(cur) + 1) % values.length] as T);
    }, TOUR_INTERVAL_MS);
    return () => window.clearTimeout(id);
  }, [running, value, values]);

  useEffect(() => {
    const el = sectionRef.current;
    if (!el || !("IntersectionObserver" in window)) return; // absent = in view
    const io = new IntersectionObserver((entries) => setInView(entries[entries.length - 1]?.isIntersecting ?? true), { threshold: 0.25 });
    io.observe(el);
    return () => io.disconnect();
  }, []);

  const select = useCallback((v: T) => {
    setValue(v);
    setChoice("off"); // the visitor is driving
  }, []);
  const toggle = useCallback(() => setChoice(playing ? "off" : "on"), [playing]);
  // M-4: Base UI does not call onValueChange when the already-active tab is clicked, but that is still the
  // visitor driving. Sets the choice only (never the value), so it cannot undo the change a click on another tab made.
  const takeOver = useCallback(() => setChoice("off"), []);

  const stageProps = {
    // Touch has no hover; a tap would otherwise leave the tour "hovered" and paused until the next tap.
    onPointerEnter: (e: React.PointerEvent) => {
      if (e.pointerType !== "touch") setHover(true);
    },
    onPointerLeave: () => setHover(false),
    onFocus: () => setFocus(true),
    onBlur: (e: React.FocusEvent<HTMLElement>) => {
      if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setFocus(false);
    },
  };

  return { value, select, playing, running, reduced, toggle, takeOver, sectionRef, stageProps };
}
