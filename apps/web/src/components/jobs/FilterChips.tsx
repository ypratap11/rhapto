import { cn } from "cn";
import type { FitFilter, PostedWithin, SearchState } from "@/lib/search-state";

/** Just an id + display label — the full `SourceSetting` (enabled, fields, key_set, needs_key) is
 * the Settings page's concern, not this chip row's. Callers map `SourceSetting.id` to `source`. */
export type SourceOption = { source: string; label: string };

const DATE_OPTIONS: { value: PostedWithin; label: string }[] = [
  { value: "24h", label: "24h" },
  { value: "7d", label: "7d" },
  { value: "30d", label: "30d" },
  { value: "90d", label: "90d" },
  { value: "any", label: "Any time" },
];

const FIT_OPTIONS: { value: FitFilter; label: string }[] = [
  { value: "75", label: "75+" },
  { value: "60", label: "60+" },
  { value: "all", label: "All fits" },
];

/** A segmented option: the pressed one is a raised pill on the muted track, the rest plain text. */
function Segment({ pressed, onClick, children }: { pressed: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      onClick={onClick}
      className={cn(
        "rounded-full px-3 py-1 text-sm font-medium transition-colors max-md:min-h-11 focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/50",
        pressed ? "bg-surface text-foreground shadow-card" : "text-muted-foreground hover:text-foreground",
      )}
    >
      {children}
    </button>
  );
}

/** A source toggle: an outline pill, filled with the primary colour while on. */
function Chip({ pressed, onClick, children }: { pressed: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      onClick={onClick}
      className={cn(
        "rounded-full border px-3 py-1 text-sm font-medium transition-colors max-md:min-h-11 focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/50",
        pressed ? "border-primary bg-primary text-primary-foreground" : "border-border bg-surface text-foreground hover:bg-surface-muted",
      )}
    >
      {children}
    </button>
  );
}

/** The small visible label before a track. Hidden from assistive tech: the group's own aria-label already names it. */
function GroupLabel({ children }: { children: React.ReactNode }) {
  return (
    <span aria-hidden="true" className="text-xs font-medium text-muted-foreground">
      {children}
    </span>
  );
}

export function FilterChips({
  value,
  onChange,
  sources,
}: {
  value: SearchState;
  onChange: (next: SearchState) => void;
  sources: SourceOption[];
}) {
  function toggleSource(source: string) {
    const has = value.sources.includes(source);
    onChange({ ...value, sources: has ? value.sources.filter((s) => s !== source) : [...value.sources, source] });
  }

  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-3">
      <div className="flex items-center gap-2">
        <GroupLabel>Posted</GroupLabel>
        <div role="group" aria-label="Date posted" className="flex flex-wrap gap-0.5 rounded-full bg-surface-muted p-1">
          {DATE_OPTIONS.map((opt) => (
            <Segment key={opt.value} pressed={value.posted_within === opt.value} onClick={() => onChange({ ...value, posted_within: opt.value })}>
              {opt.label}
            </Segment>
          ))}
        </div>
      </div>
      {sources.length > 0 ? (
        <div role="group" aria-label="Source" className="flex flex-wrap gap-1.5">
          {sources.map((s) => (
            <Chip key={s.source} pressed={value.sources.includes(s.source)} onClick={() => toggleSource(s.source)}>
              {s.label}
            </Chip>
          ))}
        </div>
      ) : null}
      <div className="flex items-center gap-2">
        <GroupLabel>Fit</GroupLabel>
        <div role="group" aria-label="Fit" className="flex flex-wrap gap-0.5 rounded-full bg-surface-muted p-1">
          {FIT_OPTIONS.map((opt) => (
            <Segment key={opt.value} pressed={value.fit === opt.value} onClick={() => onChange({ ...value, fit: opt.value })}>
              {opt.label}
            </Segment>
          ))}
        </div>
      </div>
    </div>
  );
}
