"use client";

import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { JobFilters } from "@/lib/api/queries";
import { REGION_LABEL } from "@/lib/fit";

const ALL_TRACKS = "__all__";

// The active segment must read as "selected" without reaching for the accent
// (reserved for primary actions like Tailor/Add job/Poll now), and the
// `secondary` button variant is too close in tone to the page background to
// read as clearly selected next to the `outline` inactive segments — so this
// is a plain neutral filled style instead of a `Button` variant.
const ACTIVE_SEGMENT_CLASS = "bg-foreground text-background border-foreground hover:bg-foreground/90 hover:text-background";

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
      <Select value={filters.region} onValueChange={(value: string | null) => value && onChange({ ...filters, region: value as JobFilters["region"] })}>
        <SelectTrigger className="w-40" aria-label="Region">
          {/* Spelled out rather than left to SelectValue's default: until the popup has been
              opened once it has no item labels to look up and falls back to the raw value. */}
          <SelectValue>{(value: string) => REGION_LABEL[value as JobFilters["region"]]}</SelectValue>
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="preferred">{REGION_LABEL.preferred}</SelectItem>
          <SelectItem value="us">{REGION_LABEL.us}</SelectItem>
          <SelectItem value="any">{REGION_LABEL.any}</SelectItem>
        </SelectContent>
      </Select>
      <Tabs value={filters.tab} onValueChange={(v) => v && onChange({ ...filters, tab: v as JobFilters["tab"] })}>
        <TabsList aria-label="Jobs tab">
          <TabsTrigger value="new">New</TabsTrigger>
          <TabsTrigger value="tailored">Tailored</TabsTrigger>
          <TabsTrigger value="low">Low fit</TabsTrigger>
        </TabsList>
      </Tabs>
      <div className="flex gap-1" role="group" aria-label="Sort">
        <Button
          type="button"
          variant="outline"
          className={filters.sort === "fit" ? ACTIVE_SEGMENT_CLASS : undefined}
          size="sm"
          aria-pressed={filters.sort === "fit"}
          onClick={() => onChange({ ...filters, sort: "fit" })}
        >
          By fit
        </Button>
        <Button
          type="button"
          variant="outline"
          className={filters.sort === "newest" ? ACTIVE_SEGMENT_CLASS : undefined}
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
