import type { PerSource } from "@/lib/api/portal";
import { SOURCE_LABEL } from "@/lib/fit";

type Stat = PerSource[string];

const RATE_LIMITED = "rate-limited (quota used up, try again later)";

function resetText(resetAt: string): string | null {
  const date = new Date(resetAt);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

function counts(stat: Stat): string {
  const q = stat.quota;
  const left = q && q.remaining != null && q.limit != null ? ` · ${q.remaining} of ${q.limit} requests left` : "";
  return `${stat.found} found · ${stat.new} new${left}`;
}

function partialNote(stat: Stat): string {
  const boards = stat.failed_boards ?? [];
  if (boards.length === 0) return "";
  const what = boards.map((b) => `${b.name} ${b.message}`).join("; ");
  return ` (${boards.length} ${boards.length === 1 ? "board" : "boards"} failed: ${what})`;
}

function describe(label: string, stat: Stat): string {
  // An old payload carries `error` and no `state`; the schema default would say "ok", so an
  // error with no explicit state is read as a failure.
  const state = stat.error && (!stat.state || stat.state === "ok") ? "failed" : (stat.state ?? "ok");
  switch (state) {
    case "partial":
      return `${label} ${counts(stat)}${partialNote(stat)}`;
    case "rate_limited":
      return `${label} ${RATE_LIMITED}`;
    case "unavailable":
      return `${label}: ${stat.error ?? "not available right now"}`;
    case "quota_exhausted": {
      const when = stat.quota?.reset_at ? resetText(stat.quota.reset_at) : null;
      return when ? `${label} quota used up until ${when}` : `${label} ${RATE_LIMITED}`;
    }
    case "failed":
      return `${label} failed (${stat.error ?? "unknown error"})`;
    default:
      return `${label} ${counts(stat)}`;
  }
}

export function SourceReport({ perSource }: { perSource: PerSource | null }) {
  if (!perSource) return null;
  const entries = Object.entries(perSource);
  if (entries.length === 0) return null;

  const parts = entries.map(([source, stat]) => describe(SOURCE_LABEL[source] ?? source, stat));

  return <p className="break-words text-sm text-muted-foreground">{parts.join(" · ")}</p>;
}
