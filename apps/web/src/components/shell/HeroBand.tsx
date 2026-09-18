import { StitchMotif } from "@/components/ui/stitch-motif";
import { cn } from "cn";

const TONE_CLASS = { peach: "bg-band-peach", mint: "bg-band-mint", sand: "bg-band-sand" } as const;
const HEIGHT_CLASS = { tall: "min-h-band-tall", short: "min-h-band-short" } as const;

/** Full-bleed tinted band. The shell's main element is width-capped and padded, so the band
 * cancels both with negative margins to reach the viewport edges (spec §8: full-width). */
export function HeroBand({
  tone,
  height = "short",
  children,
}: {
  tone: "peach" | "mint" | "sand";
  height?: "tall" | "short";
  children: React.ReactNode;
}) {
  return (
    <div
      data-testid="hero-band"
      className={cn(
        "relative -mx-6 -mt-8 mb-8 overflow-hidden border-b border-border px-6 py-8 text-foreground",
        TONE_CLASS[tone],
        HEIGHT_CLASS[height],
      )}
    >
      <StitchMotif className="pointer-events-none absolute inset-y-0 right-0 hidden h-full w-1/3 md:block" />
      <div className="relative mx-auto flex h-full max-w-6xl flex-col justify-center gap-3">{children}</div>
    </div>
  );
}
