"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { usePrefersReducedMotion } from "@/lib/motion";

/** One slide every 4 s. The progress bar's CSS duration is set from this same constant. */
export const TOUR_INTERVAL_MS = 4000;

/** A touch that moved less than this many px in total and ended within TAP_MAX_MS is a tap; anything else is a scroll or swipe. */
const TAP_MAX_MOVE_PX = 10;
const TAP_MAX_MS = 500;

/** Self-playing tour state. Autoplay is held (not cancelled) while the pointer or focus is in the stage or
 * while the tour is off-screen; a user tab selection turns it off; the play button turns it on, even under
 * reduced motion. running = playing && !userTookOver && !hovered && !focusWithin && !touching && inView && !reducedMotion,
 * with `choice` folding playing / userTookOver / the reduced-motion override into one value. */
export function useTourAutoplay<T extends string>(values: readonly T[]) {
  const [value, setValue] = useState<T>(values[0] as T);
  // null: the visitor has not chosen, follow the system preference. "off": they picked a tab or pressed
  // Pause. "on": they pressed Play.
  const [choice, setChoice] = useState<"on" | "off" | null>(null);
  const [hover, setHover] = useState(false);
  const [focus, setFocus] = useState(false);
  const [touching, setTouching] = useState(false);
  const touch = useRef<{ x: number; y: number; at: number; moved: number } | null>(null);
  const [inView, setInView] = useState(true);
  const sectionRef = useRef<HTMLElement | null>(null);
  const reduced = usePrefersReducedMotion();

  const playing = choice === null ? !reduced : choice === "on";
  const running = playing && !hover && !focus && !touching && inView;

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
    // Touch has no hover: a finger down on the stage holds autoplay like hover. A tap (short, barely moved)
    // means the visitor is driving, like a tab click; a scroll or swipe that happens to start here resumes it.
    // Passive React props, no preventDefault. (Not onScroll: the programmatic scrollLeft re-centring fires scroll events too.)
    onTouchStart: (e: React.TouchEvent) => {
      const t = e.touches[0];
      touch.current = { x: t?.clientX ?? 0, y: t?.clientY ?? 0, at: Date.now(), moved: 0 };
      setTouching(true);
    },
    onTouchMove: (e: React.TouchEvent) => {
      const t = e.touches[0];
      const s = touch.current;
      if (!t || !s) return;
      s.moved = Math.max(s.moved, Math.hypot(t.clientX - s.x, t.clientY - s.y));
    },
    onTouchEnd: () => {
      const s = touch.current;
      touch.current = null;
      setTouching(false);
      if (s && s.moved < TAP_MAX_MOVE_PX && Date.now() - s.at < TAP_MAX_MS) setChoice("off");
    },
    onTouchCancel: () => {
      touch.current = null;
      setTouching(false);
    },
    onFocus: () => setFocus(true),
    onBlur: (e: React.FocusEvent<HTMLElement>) => {
      if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setFocus(false);
    },
  };

  return { value, select, playing, running, reduced, toggle, takeOver, sectionRef, stageProps };
}
