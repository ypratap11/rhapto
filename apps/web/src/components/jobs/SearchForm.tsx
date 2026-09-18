import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import type { Remote, SearchState } from "@/lib/search-state";

/** Just what the Field select needs — the full `TaxonomyField` (roles, aggregator categories) is
 * more than this form ever reads. */
export type FieldOption = { id: string; name: string };

// The Select can't represent `field: null` with an empty string value, so "My tracks" gets its own
// sentinel that the handlers translate back to null.
const MY_TRACKS = "__tracks__";

const REMOTE_LABEL: Record<Remote, string> = {
  include: "Include remote",
  only: "Remote only",
  exclude: "Exclude remote",
};

export function SearchForm({
  value,
  onChange,
  onSubmit,
  fields,
  pending,
}: {
  value: SearchState;
  onChange: (next: SearchState) => void;
  onSubmit: () => void;
  fields: FieldOption[];
  pending: boolean;
}) {
  return (
    <form
      className="flex flex-wrap items-end gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit();
      }}
    >
      <div className="flex min-w-48 flex-1 flex-col gap-1">
        <Label htmlFor="search-title">Title</Label>
        <Input
          id="search-title"
          aria-label="Title"
          value={value.query}
          onChange={(e) => onChange({ ...value, query: e.target.value })}
          placeholder="Job title or keywords"
        />
      </div>
      <div className="flex min-w-48 flex-1 flex-col gap-1">
        <Label htmlFor="search-location">Location</Label>
        <Input
          id="search-location"
          aria-label="Location"
          value={value.location}
          onChange={(e) => onChange({ ...value, location: e.target.value })}
          placeholder="Anywhere — defaults to your home location"
        />
      </div>
      <div className="flex flex-col gap-1">
        <Label>Field</Label>
        <Select
          value={value.field ?? MY_TRACKS}
          onValueChange={(v) => {
            if (v === null) return;
            onChange({ ...value, field: v === MY_TRACKS ? null : v });
          }}
        >
          <SelectTrigger aria-label="Field">
            <SelectValue>{(v: string | null) => (v === MY_TRACKS || v === null ? "My tracks" : (fields.find((f) => f.id === v)?.name ?? v))}</SelectValue>
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={MY_TRACKS}>My tracks</SelectItem>
            {fields.map((f) => (
              <SelectItem key={f.id} value={f.id}>
                {f.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="flex flex-col gap-1">
        <Label>Remote</Label>
        <Select
          value={value.remote}
          onValueChange={(v) => {
            if (v === null) return;
            onChange({ ...value, remote: v as Remote });
          }}
        >
          <SelectTrigger aria-label="Remote">
            <SelectValue>{(v: string | null) => REMOTE_LABEL[(v ?? "include") as Remote]}</SelectValue>
          </SelectTrigger>
          <SelectContent>
            {(Object.keys(REMOTE_LABEL) as Remote[]).map((r) => (
              <SelectItem key={r} value={r}>
                {REMOTE_LABEL[r]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <Button type="submit" disabled={pending}>
        Search
      </Button>
    </form>
  );
}
