"use client";

import { useEffect, useId, useRef } from "react";
import { usePrefersReducedMotion } from "@/lib/motion";

/** Served from public/media, a prefix Cloudflare Access bypasses (apps/web/src/lib/edge-visibility.json). */
export const COMMERCIAL_SRC = "/media/rhapto-commercial.mp4";
export const COMMERCIAL_POSTER = "/media/rhapto-commercial-poster.webp";
export const COMMERCIAL_LABEL = "Rhapto in 34 seconds";
export const COMMERCIAL_DESCRIPTION =
  "The video shows an invented 40% resume line being blocked, a line backed by a verified fact replacing it, and then the person applying themselves on the employer's own site.";

/** Wide screens only: phones never autoplay and never fetch the file until the viewer presses play. */
const WIDE_QUERY = "(min-width: 1024px)";

/** The 34-second commercial. Playing by tap or click is with sound. On a wide screen, with motion allowed,
 * it also starts muted once when it scrolls into view; the viewer can unmute from the controls.
 * `preload="none"` keeps the 8 MB file off the wire until play. */
export function CommercialVideo() {
  const ref = useRef<HTMLVideoElement | null>(null);
  const descId = useId();
  const reduced = usePrefersReducedMotion(); // true until mounted, so nothing autoplays on the server pass

  useEffect(() => {
    const el = ref.current;
    if (!el || reduced) return;
    if (typeof window.matchMedia !== "function" || !window.matchMedia(WIDE_QUERY).matches) return;
    if (!("IntersectionObserver" in window)) return;
    let started = false;
    const io = new IntersectionObserver(
      (entries) => {
        if (started || !entries.some((e) => e.isIntersecting)) return;
        started = true;
        io.disconnect(); // once: never restart a video the viewer has paused or finished
        el.muted = true; // browsers only allow autoplay when muted
        void el.play()?.catch(() => {}); // blocked autoplay just leaves the poster and controls
      },
      { threshold: 0.5 },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [reduced]);

  return (
    <section aria-labelledby="commercial-heading" className="reveal mx-auto mb-16 w-full max-w-5xl sm:mb-20">
      <h2 id="commercial-heading" className="mb-6 text-center font-heading text-2xl font-semibold tracking-tight sm:text-3xl">
        See it in 34 seconds
      </h2>
      <video
        ref={ref}
        src={COMMERCIAL_SRC}
        poster={COMMERCIAL_POSTER}
        controls
        playsInline
        preload="none"
        aria-label={COMMERCIAL_LABEL}
        aria-describedby={descId}
        className="aspect-video w-full rounded-card border border-border bg-surface shadow-card"
      />
      <p id={descId} className="mx-auto mt-3 max-w-2xl text-center text-sm text-muted-foreground">
        {COMMERCIAL_DESCRIPTION}
      </p>
    </section>
  );
}
