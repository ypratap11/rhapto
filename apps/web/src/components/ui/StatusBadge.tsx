import { Badge } from "@/components/ui/badge";
import type { Tone } from "@/lib/status";

// 6px chips (spec §8): the Badge base is a 999px pill, so every tone overrides the radius.
const TONE_CLASS: Record<Tone, string> = {
  neutral: "rounded-chip border-border bg-surface-muted text-foreground",
  muted: "rounded-chip border-border bg-surface-muted text-muted-foreground",
  high: "rounded-chip border-fit-high/30 bg-fit-high-bg text-fit-high",
  mid: "rounded-chip border-fit-mid/30 bg-fit-mid-bg text-fit-mid",
  primary: "rounded-chip border-primary/30 bg-primary/10 text-primary",
  danger: "rounded-chip border-destructive/30 bg-destructive/10 text-destructive",
};

export function StatusBadge({ tone, children }: { tone: Tone; children: React.ReactNode }) {
  return (
    <Badge variant="outline" className={`font-normal ${TONE_CLASS[tone]}`}>
      {children}
    </Badge>
  );
}
