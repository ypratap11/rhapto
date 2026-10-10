import { Badge } from "@/components/ui/badge";
import type { Tone } from "@/lib/status";

// Pills, like Badge. Deliberately reverses the 2026-09 "6px chips" decision (spec 2026-10-09 section 3).
const TONE_CLASS: Record<Tone, string> = {
  neutral: "border-border bg-surface-muted text-foreground",
  muted: "border-border bg-surface-muted text-muted-foreground",
  high: "border-fit-high/30 bg-fit-high-bg text-fit-high",
  mid: "border-fit-mid/30 bg-fit-mid-bg text-fit-mid",
  primary: "border-primary/30 bg-primary/10 text-primary",
  danger: "border-destructive/30 bg-destructive/10 text-destructive",
};

export function StatusBadge({ tone, children }: { tone: Tone; children: React.ReactNode }) {
  return (
    <Badge variant="outline" className={`font-normal ${TONE_CLASS[tone]}`}>
      {children}
    </Badge>
  );
}
