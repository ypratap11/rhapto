import { StatusBadge } from "@/components/ui/StatusBadge";
import type { Block } from "@/lib/api/queries";

/** A plain-words name for where a line came from: the employer, else the role, else a generic label. */
export function sourceLabel(block: Block): string {
  return block.org || block.role || "Your experience";
}

export function SourceBlockCard({ block }: { block: Block | null }) {
  if (!block) return <p className="text-sm text-muted-foreground">Select a line to see which part of your resume it came from.</p>;
  return (
    <section className="space-y-2 rounded-md border border-border bg-card p-4 text-sm">
      <div className="flex items-center justify-between gap-2">
        <span className="font-medium">{sourceLabel(block)}</span>
        <StatusBadge tone={block.verified ? "high" : "muted"}>{block.verified ? "confirmed" : "not confirmed"}</StatusBadge>
      </div>
      <p className="text-muted-foreground">{[block.role, block.period].filter(Boolean).join(" · ")}</p>
      {block.metric ? <p className="font-mono text-xs">{block.metric}</p> : null}
      <p>{block.content}</p>
      {block.tags.length ? <p className="text-xs text-muted-foreground">{block.tags.join(", ")}</p> : null}
      <details className="text-xs text-muted-foreground">
        <summary className="flex min-h-11 cursor-pointer items-center">Details</summary>
        <p className="font-mono">{block.id}</p>
      </details>
    </section>
  );
}
