import { cn } from "cn";
import type { FitFilter, PostedWithin, SearchState } from "@/lib/search-state";

/** Just an id + display label — the full `SourceSetting` (enabled, fields, key_set, needs_key) is
 * the Settings page's concern, not this chip row's. Callers map `SourceSetting.id` to `source`. */
export type SourceOption = { source: string; label: string };

const DATE_OPTIONS: { value: PostedWithin; label: string }[] = [
  { value: "24h", label: "24h" },
  { value: "7d", label: "7d" },
  { value: "30d", label: "30d" },
  { value: "any", label: "Any time" },
];

const FIT_OPTIONS: { value: FitFilter; label: string }[] = [
  { value: "75", label: "75+" },
  { value: "60", label: "60+" },
  { value: "all", label: "All fits" },
];

function Chip({ pressed, onClick, children }: { pressed: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      onClick={onClick}
      className={cn(
        "rounded-chip border px-2.5 py-1 text-sm font-medium transition-colors",
        pressed ? "border-primary bg-primary text-primary-foreground" : "border-border bg-surface text-foreground hover:bg-surface-muted",
      )}
    >
      {children}
    </button>
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
    <div className="flex flex-wrap items-center gap-4">
      <div role="group" aria-label="Date posted" className="flex flex-wrap gap-1.5">
        {DATE_OPTIONS.map((opt) => (
          <Chip key={opt.value} pressed={value.posted_within === opt.value} onClick={() => onChange({ ...value, posted_within: opt.value })}>
            {opt.label}
          </Chip>
        ))}
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
      <div role="group" aria-label="Fit" className="flex flex-wrap gap-1.5">
        {FIT_OPTIONS.map((opt) => (
          <Chip key={opt.value} pressed={value.fit === opt.value} onClick={() => onChange({ ...value, fit: opt.value })}>
            {opt.label}
          </Chip>
        ))}
      </div>
    </div>
  );
}
