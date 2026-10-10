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
 * this component's unit tests. The "glow" tone (the front page only) is a faint warm wash with centred
 * content and no decoration. */
export function HeroBand({
  tone,
  height = "short",
  children,
}: {
  tone: "peach" | "mint" | "sand" | "glow";
  height?: "tall" | "short";
  children: React.ReactNode;
}) {
  const glow = tone === "glow";
  // Glow: the band's own bottom padding (py-8 / sm:py-12) plus mb-8 makes the gap to the next section 64px on
  // phones and 80px from sm, the same as the sections' mb-16 / sm:mb-20.
  return (
    <div
      data-testid="hero-band"
      className={cn(
        "relative mx-[calc(50%-50vw)] -mt-8 w-screen overflow-hidden px-6 py-8 text-foreground",
        glow ? "mb-8 border-b-0 sm:py-12" : "mb-8 border-b border-border",
        TONE_CLASS[tone],
        HEIGHT_CLASS[height],
      )}
    >
      {glow ? null : <StitchMotif className="pointer-events-none absolute inset-y-0 right-0 hidden h-full w-1/3 md:block" />}
      {/* Glow: max-w-5xl is the front page's one content width (steps, tour, proof and closing use it
          too). Other tones keep max-w-6xl: they are in-app pages whose content is left-aligned. */}
      <div className={cn("relative mx-auto flex h-full w-full flex-col justify-center gap-3", glow ? "max-w-5xl items-center text-center" : "max-w-6xl")}>
        {children}
      </div>
    </div>
  );
}
