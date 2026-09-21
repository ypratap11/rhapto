"use client";

import { useMemo, useState } from "react";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { ApplicationOut } from "@/lib/api/queries";
import { formatDate } from "@/lib/format";
import { PIPELINE_STATUSES, STATUS_LABEL, statusTone, type ApplicationStatus, type PipelineStatus } from "@/lib/status";

type SortKey = "updated" | "applied" | "company";

const SORT_OPTIONS: { value: SortKey; label: string }[] = [
  { value: "updated", label: "Updated" },
  { value: "applied", label: "Applied date" },
  { value: "company", label: "Company" },
];

function isPipelineStatus(value: string): value is PipelineStatus {
  return (PIPELINE_STATUSES as readonly string[]).includes(value);
}

function isSortKey(value: string): value is SortKey {
  return value === "updated" || value === "applied" || value === "company";
}

function matchesSearch(application: ApplicationOut, query: string): boolean {
  if (!query) return true;
  const q = query.toLowerCase();
  return (application.job.company ?? "").toLowerCase().includes(q) || (application.job.title ?? "").toLowerCase().includes(q);
}

function sortApplications(rows: ApplicationOut[], sort: SortKey): ApplicationOut[] {
  const sorted = [...rows];
  switch (sort) {
    case "applied":
      sorted.sort((a, b) => (b.applied_at ?? "").localeCompare(a.applied_at ?? ""));
      break;
    case "company":
      sorted.sort((a, b) => (a.job.company ?? "").localeCompare(b.job.company ?? ""));
      break;
    case "updated":
    default:
      sorted.sort((a, b) => b.updated_at.localeCompare(a.updated_at));
      break;
  }
  return sorted;
}

export function ApplicationList({
  applications,
  selectedId,
  onSelect,
}: {
  applications: ApplicationOut[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const [tab, setTab] = useState<PipelineStatus>("applied");
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<SortKey>("updated");

  const rows = useMemo(() => {
    const inTab = applications.filter((a) => a.status === tab && matchesSearch(a, search));
    return sortApplications(inTab, sort);
  }, [applications, tab, search, sort]);

  return (
    <div className="space-y-3">
      {/* Search and sort share a row and both shrink; the five tabs get a row of their own. They
        * used to sit beside the tabs, which at 360px overflowed the column and painted over the
        * detail pane -- `min-w-0` is what lets the input give way instead of pushing. */}
      <div className="flex items-center gap-2">
        <Input
          aria-label="Search applications"
          placeholder="Search company or role"
          className="min-w-0 flex-1"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <Select value={sort} onValueChange={(value) => typeof value === "string" && isSortKey(value) && setSort(value)}>
          <SelectTrigger aria-label="Sort by" size="sm" className="shrink-0">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {SORT_OPTIONS.map((opt) => (
              <SelectItem key={opt.value} value={opt.value}>
                {opt.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <Tabs value={tab} onValueChange={(value) => typeof value === "string" && isPipelineStatus(value) && setTab(value)}>
        {/* Scrolls rather than overflows when the five labels exceed a narrow column; the
          * scrollbar chrome itself is hidden because it renders as a stub beside the last tab. */}
        <TabsList
          aria-label="Pipeline status"
          className="w-full justify-start overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
        >
          {PIPELINE_STATUSES.map((s) => (
            <TabsTrigger key={s} value={s}>
              {STATUS_LABEL[s]}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>
      <ul className="space-y-2">
        {rows.length === 0 ? (
          <li className="rounded-card border border-dashed border-border px-3 py-6 text-center text-sm text-muted-foreground">
            No applications here yet.
          </li>
        ) : (
          rows.map((a) => {
            const selected = a.id === selectedId;
            return (
              <li key={a.id}>
                <button
                  type="button"
                  aria-current={selected}
                  onClick={() => onSelect(a.id)}
                  className={`w-full text-left rounded-card border p-3 shadow-card hover-lift ${selected ? "border-primary" : "border-border"} bg-surface`}
                >
                  <p className="truncate text-sm font-semibold text-foreground">{a.job.company ?? "Unknown company"}</p>
                  <p className="text-sm text-muted-foreground">{a.job.title ?? "Untitled role"}</p>
                  {/* No status pill: every card here is already filtered to the active tab, so it
                    * would repeat the tab's own name. Only a status the tab does not imply, and
                    * the dates, earn a line. */}
                  <div className="mt-2 flex flex-wrap items-center gap-2">
                    {a.status === tab ? null : (
                      <StatusBadge tone={statusTone(a.status)}>{STATUS_LABEL[a.status as ApplicationStatus] ?? a.status}</StatusBadge>
                    )}
                    {a.applied_at ? <span className="text-xs text-muted-foreground">Applied · {formatDate(a.applied_at)}</span> : null}
                    {a.follow_up_at ? <StatusBadge tone="mid">Follow up {formatDate(a.follow_up_at)}</StatusBadge> : null}
                  </div>
                </button>
              </li>
            );
          })
        )}
      </ul>
    </div>
  );
}
