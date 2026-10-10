import { StitchMotif } from "@/components/ui/stitch-motif";
import { cn } from "cn";

const TONE_CLASS = { peach: "bg-band-peach", mint: "bg-band-mint", sand: "bg-band-sand", glow: "bg-hero-glow" } as const;
const HEIGHT_CLASS = { tall: "min-h-band-tall", short: "min-h-band-short" } as const;

/** Full-bleed tinted band. The shell's main element is width-capped (`max-w-6xl`) and centered, so
 * a fixed `-mx-6` only cancels main's own padding — it stops at main's box edge, not the viewport,
 * on any screen wider than the cap (spec §8: full-width). `w-screen` + `mx-[calc(50%-50vw)]` is the
 * standard breakout: because main is itself centered on the page, the parent-width term in `50%`
 * cancels algebraically against main's offset from the viewport, so this reaches the true viewport
 * edges regardless of main's width or padding. `100vw` includes the scrollbar's width though, so on
 * a page tall enough to scroll this would overflow the real viewport by a few pixels; `Shell`'s root
 * carries `overflow-x-clip` to swallow that instead of letting it grow into a horizontal scrollbar.
 * Layout correctness here is algebraic, not something jsdom can render — confirmed visually, not by
 * this component's unit tests. The "glow" tone (the front page only: /) swaps the stitch motif
 * for a radial gradient and two soft shapes. */
export function HeroBand({
  tone,
  height = "short",
  children,
}: {
  tone: "peach" | "mint" | "sand" | "glow";
  height?: "tall" | "short";
  children: React.ReactNode;
}) {
  return (
    <div
      data-testid="hero-band"
      className={cn(
        "relative mx-[calc(50%-50vw)] -mt-8 mb-8 w-screen overflow-hidden border-b border-border px-6 py-8 text-foreground",
        TONE_CLASS[tone],
        HEIGHT_CLASS[height],
      )}
    >
      {tone === "glow" ? (
        <>
          <div data-decor aria-hidden="true" className="pointer-events-none absolute -right-16 -top-24 size-72 rounded-full bg-decor-amber opacity-20" />
          <div data-decor aria-hidden="true" className="pointer-events-none absolute -bottom-28 -left-24 size-64 rounded-full bg-decor-teal opacity-15" />
        </>
      ) : (
        <StitchMotif className="pointer-events-none absolute inset-y-0 right-0 hidden h-full w-1/3 md:block" />
      )}
      <div className="relative mx-auto flex h-full max-w-6xl flex-col justify-center gap-3">{children}</div>
    </div>
  );
}
