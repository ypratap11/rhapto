"use client";

import { useEffect } from "react";
import { usePrefersReducedMotion } from "@/lib/motion";

/** Fades the `.reveal` sections in once as they scroll into view. Arms only sections that start below the
 * fold, only when IntersectionObserver exists and motion is allowed; with no JS, no observer or reduced
 * motion nothing is armed and everything is visible. Once a section is "in" it stays in (no re-hide on
 * scroll-up). The attribute is set on the DOM directly, after mount, so it cannot cause a hydration mismatch. */
export function RevealOnScroll() {
  const reduced = usePrefersReducedMotion(); // true on the server and the hydration pass, so nothing arms before mount
  useEffect(() => {
    if (reduced || !("IntersectionObserver" in window)) return;
    const els = [...document.querySelectorAll<HTMLElement>(".reveal")];
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (!e.isIntersecting) continue;
          (e.target as HTMLElement).dataset.reveal = "in";
          io.unobserve(e.target);
        }
      },
      { rootMargin: "0px 0px -8% 0px" },
    );
    for (const el of els) {
      if (el.getBoundingClientRect().top < window.innerHeight) continue; // already on screen: leave it visible
      el.dataset.reveal = "armed";
      io.observe(el);
    }
    return () => {
      io.disconnect();
      for (const el of els) if (el.dataset.reveal === "armed") delete el.dataset.reveal; // never leave anything hidden
    };
  }, [reduced]);
  return null;
}
