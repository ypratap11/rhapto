import { Badge } from "@/components/ui/badge";
import type { Tone } from "@/lib/status";

const TONE_CLASS: Record<Tone, string> = {
  slate: "bg-slate-100 text-slate-700 border-slate-200",
  amber: "bg-amber-100 text-amber-800 border-amber-200",
  green: "bg-green-100 text-green-800 border-green-200",
  zinc: "bg-zinc-100 text-zinc-600 border-zinc-200",
  red: "bg-red-100 text-red-800 border-red-200",
  indigo: "bg-indigo-100 text-indigo-800 border-indigo-200",
};

export function StatusBadge({ tone, children }: { tone: Tone; children: React.ReactNode }) {
  return (
    <Badge variant="outline" className={`font-normal ${TONE_CLASS[tone]}`}>
      {children}
    </Badge>
  );
}
