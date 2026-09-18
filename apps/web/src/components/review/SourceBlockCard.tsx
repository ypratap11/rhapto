import { StatusBadge } from "@/components/ui/StatusBadge";
import type { Block } from "@/lib/api/queries";

export function SourceBlockCard({ block }: { block: Block | null }) {
  if (!block) return <p className="text-sm text-muted-foreground">Select a bullet to see the block it came from.</p>;
  return (
    <section className="space-y-2 rounded-md border border-border bg-card p-4 text-sm">
      <div className="flex items-center justify-between">
        <span className="font-mono text-xs">{block.id}</span>
        <StatusBadge tone={block.verified ? "high" : "muted"}>{block.verified ? "verified" : "unverified"}</StatusBadge>
      </div>
      <p className="text-muted-foreground">{[block.type, block.org, block.role, block.period].filter(Boolean).join(" · ")}</p>
      {block.metric ? <p className="font-mono text-xs">{block.metric}</p> : null}
      <p>{block.content}</p>
      {block.tags.length ? <p className="text-xs text-muted-foreground">{block.tags.join(", ")}</p> : null}
    </section>
  );
}
