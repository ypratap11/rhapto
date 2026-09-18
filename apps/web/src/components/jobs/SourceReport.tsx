import type { PerSource } from "@/lib/api/portal";
import { SOURCE_LABEL } from "@/lib/fit";

export function SourceReport({ perSource }: { perSource: PerSource | null }) {
  if (!perSource) return null;
  const entries = Object.entries(perSource);
  if (entries.length === 0) return null;

  const parts = entries.flatMap(([source, stat]) => {
    const label = SOURCE_LABEL[source] ?? source;
    if (stat.error) return [`${label} failed (${stat.error})`];
    return [`${label} ${stat.found} found`, `${stat.new} new`];
  });

  return <p className="text-sm text-muted-foreground">{parts.join(" · ")}</p>;
}
