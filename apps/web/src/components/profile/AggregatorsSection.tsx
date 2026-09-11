"use client";

import { useState } from "react";
import { toast } from "sonner";
import { ApiErrorBanner } from "@/components/shell/ApiErrorBanner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api/client";
import { useAggregators, usePutAggregators, useSources, type AggregatorEntry, type SourceInfoOut } from "@/lib/api/queries";
import { joinList, splitList } from "@/lib/profile-forms";
import { SwitchField } from "./fields";

/** Self-contained: loads its own aggregators and sources, so it can be dropped anywhere. */
export function AggregatorsSection() {
  const aggregators = useAggregators();
  const sources = useSources();
  if (aggregators.isLoading || sources.isLoading) return <Skeleton className="h-24 w-full" />;
  if (aggregators.error) return <ApiErrorBanner error={aggregators.error} />;
  if (sources.error) return <ApiErrorBanner error={sources.error} />;
  const aggregatorSources = (sources.data ?? []).filter((s) => s.kind === "aggregator");
  // Keyed by data identity (see WatchlistTab/AnswersTab) so the editable copy resets only when
  // the server data actually changes, not on every render.
  return (
    <AggregatorsBody
      key={JSON.stringify([aggregators.data ?? [], aggregatorSources])}
      saved={aggregators.data ?? []}
      aggregatorSources={aggregatorSources}
    />
  );
}

function AggregatorsBody({ saved, aggregatorSources }: { saved: AggregatorEntry[]; aggregatorSources: SourceInfoOut[] }) {
  const put = usePutAggregators();
  // Merge the registry's aggregator sources with saved rows; a source not yet saved defaults to
  // off with no keywords. This is what makes Save always write the full registry list, not just
  // the ones the user has touched.
  const [rows, setRows] = useState<AggregatorEntry[]>(() =>
    aggregatorSources.map(
      (src) =>
        saved.find((r) => r.source === src.name) ?? {
          // The registry only ever reports sources the schema enum knows, so the narrowing is safe.
          source: src.name as AggregatorEntry["source"],
          enabled: false,
          keywords: [],
        },
    ),
  );
  // Kept as raw text (see WatchlistTab.Row) rather than derived from `rows[0].keywords.join(", ")`
  // on every render, so typing a comma isn't immediately re-collapsed by the redisplay.
  const [keywordsText, setKeywordsText] = useState(() => joinList(rows[0]?.keywords ?? []));

  function setEnabled(source: string, enabled: boolean) {
    setRows((r) => r.map((row) => (row.source === source ? { ...row, enabled } : row)));
  }

  async function save() {
    const keywords = splitList(keywordsText);
    const entries = rows.map((row) => ({ ...row, keywords }));
    try {
      await put.mutateAsync(entries);
      toast.success("Saved aggregators");
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Could not save aggregators");
    }
  }

  return (
    <div className="space-y-3">
      <h3 className="text-sm font-medium">Aggregators</h3>
      <p className="text-sm text-muted-foreground">
        Aggregators search across companies instead of one board. Keywords apply to all of them; leave blank to fall back to your track keywords.
      </p>
      <div className="flex flex-wrap gap-4">
        {aggregatorSources.map((src) => {
          const row = rows.find((r) => r.source === src.name);
          return <SwitchField key={src.name} name={src.name} label={src.label} checked={row?.enabled ?? false} onCheckedChange={(v) => setEnabled(src.name, v)} />;
        })}
      </div>
      <div className="max-w-sm space-y-1">
        <Label htmlFor="aggregator-keywords">Keywords</Label>
        <Input id="aggregator-keywords" value={keywordsText} onChange={(e) => setKeywordsText(e.target.value)} placeholder="Defaults to your track keywords" />
      </div>
      <div className="flex justify-end">
        <Button onClick={save} disabled={put.isPending}>
          Save aggregators
        </Button>
      </div>
    </div>
  );
}
