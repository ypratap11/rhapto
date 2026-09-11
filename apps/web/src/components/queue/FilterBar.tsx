"use client";

import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import type { JobFilters } from "@/lib/api/queries";

const ALL_TRACKS = "__all__";

export function FilterBar({
  filters,
  onChange,
  tracks,
}: {
  filters: JobFilters;
  onChange: (next: JobFilters) => void;
  tracks: { id: string; name: string }[];
}) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Select
        value={filters.track ?? ALL_TRACKS}
        onValueChange={(value: string | null) => onChange({ ...filters, track: value && value !== ALL_TRACKS ? value : null })}
      >
        <SelectTrigger className="w-44" aria-label="Track">
          <SelectValue placeholder="All tracks" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ALL_TRACKS}>All tracks</SelectItem>
          {tracks.map((t) => (
            <SelectItem key={t.id} value={t.id}>
              {t.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <div className="flex gap-1" role="group" aria-label="Fit bucket">
        <Button
          type="button"
          variant={filters.bucket === "fit" ? "default" : "outline"}
          size="sm"
          aria-pressed={filters.bucket === "fit"}
          onClick={() => onChange({ ...filters, bucket: "fit" })}
        >
          Fit
        </Button>
        <Button
          type="button"
          variant={filters.bucket === "low" ? "default" : "outline"}
          size="sm"
          aria-pressed={filters.bucket === "low"}
          onClick={() => onChange({ ...filters, bucket: "low" })}
        >
          Low fit
        </Button>
      </div>
      <div className="flex gap-1" role="group" aria-label="Sort">
        <Button
          type="button"
          variant={filters.sort === "fit" ? "default" : "outline"}
          size="sm"
          aria-pressed={filters.sort === "fit"}
          onClick={() => onChange({ ...filters, sort: "fit" })}
        >
          By fit
        </Button>
        <Button
          type="button"
          variant={filters.sort === "newest" ? "default" : "outline"}
          size="sm"
          aria-pressed={filters.sort === "newest"}
          onClick={() => onChange({ ...filters, sort: "newest" })}
        >
          Newest
        </Button>
      </div>
    </div>
  );
}
