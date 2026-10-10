import { cn } from "cn";
import type { matchLabel } from "@/lib/coach/labels";

export type MatchLabel = ReturnType<typeof matchLabel>;

/** The coach's match label as a chip. Wording comes from `matchLabel`; this only paints it. Used by
 * MatchesStep and by the homepage tour so the two draw it the same way. */
export function MatchChip({ label }: { label: MatchLabel }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium",
        label === "Strong match" ? "bg-fit-high-bg text-fit-high" : "bg-surface-muted text-muted-foreground",
      )}
    >
      {label}
    </span>
  );
}
