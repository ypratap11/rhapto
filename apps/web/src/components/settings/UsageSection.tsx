"use client";

import Link from "next/link";
import { ApiErrorBanner } from "@/components/shell/ApiErrorBanner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useUsageSummary, type UsageRecentOut, type UsageSummaryOut } from "@/lib/api/queries";
import { formatCostUsd, formatDate, formatTokens } from "@/lib/format";

/** One KPI tile: a muted label over a proportional-figure value (dataviz: stat-tile values use
 * the font's default proportional figures, not `tabular-nums` -- that's reserved for table
 * columns, just below). */
function StatTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-border bg-surface p-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="text-xl font-medium text-foreground">{value}</p>
    </div>
  );
}

function SummaryGrid({ title, summary }: { title: string; summary: UsageSummaryOut }) {
  return (
    <div className="space-y-2">
      <h3 className="text-sm font-medium text-foreground">{title}</h3>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <StatTile label="LLM calls" value={formatTokens(summary.calls)} />
        <StatTile label="Input tokens" value={formatTokens(summary.input_tokens)} />
        <StatTile label="Output tokens" value={formatTokens(summary.output_tokens)} />
        <StatTile label="Estimated spend" value={summary.cost_usd != null ? formatCostUsd(summary.cost_usd) : "Not available"} />
      </div>
      {summary.unpriced_calls > 0 ? (
        <p className="text-xs text-muted-foreground">
          {summary.unpriced_calls} call{summary.unpriced_calls === 1 ? "" : "s"} on a model with no price on file, excluded from the estimate above.
        </p>
      ) : null}
    </div>
  );
}

function RecentRow({ row }: { row: UsageRecentOut }) {
  return (
    <TableRow>
      <TableCell className="font-medium">
        <Link
          href={`/jobs/${row.job_id}/packages/${row.package_id}`}
          className="underline-offset-2 hover:underline"
        >
          {row.company ?? "Unknown company"}
        </Link>
        <div className="text-xs font-normal text-muted-foreground">{row.job_title ?? "Untitled role"}</div>
      </TableCell>
      <TableCell>{row.model ?? "—"}</TableCell>
      <TableCell className="tabular-nums">{row.calls}</TableCell>
      <TableCell className="tabular-nums">
        {formatTokens(row.input_tokens)} in / {formatTokens(row.output_tokens)} out
      </TableCell>
      <TableCell className="tabular-nums">{row.cost_usd != null ? formatCostUsd(row.cost_usd) : "—"}</TableCell>
      <TableCell>{formatDate(row.created_at)}</TableCell>
    </TableRow>
  );
}

/** Settings' "Usage" card: all-time and last-30-day call/token/spend totals, and the 20 most
 * recent tailoring runs. Mounted directly below `LlmProviderSection` per the Settings layout. */
export function UsageSection() {
  const usage = useUsageSummary();

  if (usage.isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Usage</CardTitle>
        </CardHeader>
        <CardContent>
          <div data-testid="usage-section-skeleton" aria-hidden="true" className="space-y-2">
            <Skeleton className="h-24 w-full" />
            <Skeleton className="h-24 w-full" />
          </div>
        </CardContent>
      </Card>
    );
  }

  if (usage.error || !usage.data) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Usage</CardTitle>
        </CardHeader>
        <CardContent>
          <ApiErrorBanner error={usage.error ?? new Error("Could not load usage")} />
        </CardContent>
      </Card>
    );
  }

  const { totals, last_30_days: last30, recent } = usage.data;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Usage</CardTitle>
      </CardHeader>
      <CardContent className="space-y-6">
        <div className="grid gap-4 sm:grid-cols-2">
          <SummaryGrid title="All time" summary={totals} />
          <SummaryGrid title="Last 30 days" summary={last30} />
        </div>
        <div className="space-y-2">
          <h3 className="text-sm font-medium text-foreground">Recent runs</h3>
          {recent.length === 0 ? (
            <p className="text-sm text-muted-foreground">No tailoring runs yet.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Job</TableHead>
                  <TableHead>Model</TableHead>
                  <TableHead>Calls</TableHead>
                  <TableHead>Tokens</TableHead>
                  <TableHead>Cost</TableHead>
                  <TableHead>Created</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {recent.map((row) => (
                  <RecentRow key={row.package_id} row={row} />
                ))}
              </TableBody>
            </Table>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
