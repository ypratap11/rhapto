"use client";

import { useSyncExternalStore } from "react";

export const REDUCED_MOTION_QUERY = "(prefers-reduced-motion: reduce)";

function subscribe(onChange: () => void): () => void {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return () => {};
  const mq = window.matchMedia(REDUCED_MOTION_QUERY);
  mq.addEventListener("change", onChange);
  return () => mq.removeEventListener("change", onChange);
}
const read = (): boolean => typeof window.matchMedia === "function" && window.matchMedia(REDUCED_MOTION_QUERY).matches;
// The server and the hydration pass answer "reduced": nothing autoplays until the client has mounted and
// read the real preference, so server and client render the same markup.
const readOnServer = (): boolean => true;

/** True when the visitor asked for reduced motion. Where matchMedia does not exist there is nothing to reduce. */
export function usePrefersReducedMotion(): boolean {
  return useSyncExternalStore(subscribe, read, readOnServer);
}
