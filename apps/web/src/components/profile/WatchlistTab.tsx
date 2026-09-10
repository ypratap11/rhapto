"use client";

import { Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { ApiErrorBanner } from "@/components/shell/ApiErrorBanner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ApiError } from "@/lib/api/client";
import { useWatchlist, usePutWatchlist, type WatchlistEntry } from "@/lib/api/queries";

const SOURCES = ["greenhouse", "lever", "ashby", "smartrecruiters", "workable"] as const;

export function WatchlistTab() {
  const watchlist = useWatchlist();
  if (watchlist.isLoading) return <Skeleton className="h-40 w-full" />;
  if (watchlist.error) return <ApiErrorBanner error={watchlist.error} />;
  // See AnswersTab: keyed by data identity so the editable copy resets only when the server data
  // changes, without syncing props into state through an effect.
  return <WatchlistBody key={JSON.stringify(watchlist.data ?? [])} initial={watchlist.data ?? []} />;
}

function WatchlistBody({ initial }: { initial: WatchlistEntry[] }) {
  const put = usePutWatchlist();
  const [rows, setRows] = useState<WatchlistEntry[]>(() => initial);

  function setRow(index: number, patch: Partial<WatchlistEntry>) {
    setRows((r) => r.map((row, i) => (i === index ? { ...row, ...patch } : row)));
  }

  function removeRow(index: number) {
    setRows((r) => r.filter((_, i) => i !== index));
  }

  async function save() {
    const entries = rows.filter((r) => r.company.trim() && r.board.trim());
    const dropped = rows.length - entries.length;
    try {
      await put.mutateAsync(entries);
      toast.success(dropped > 0 ? `Saved watchlist (${dropped} empty row${dropped === 1 ? "" : "s"} ignored)` : "Saved watchlist");
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Could not save the watchlist");
    }
  }

  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">Rows here are the companies and boards the poller checks for new postings. Saving replaces the whole list.</p>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Company</TableHead>
            <TableHead>Source</TableHead>
            <TableHead>Board</TableHead>
            <TableHead className="w-10" />
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row, i) => (
            <TableRow key={i}>
              <TableCell>
                <Label htmlFor={`watch-company-${i}`} className="sr-only">
                  Company {i + 1}
                </Label>
                <Input id={`watch-company-${i}`} value={row.company} onChange={(e) => setRow(i, { company: e.target.value })} placeholder="Company" />
              </TableCell>
              <TableCell>
                <Select value={row.source} onValueChange={(v) => v && setRow(i, { source: v as WatchlistEntry["source"] })}>
                  <SelectTrigger aria-label={`Source ${i + 1}`}>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {SOURCES.map((s) => (
                      <SelectItem key={s} value={s}>
                        {s}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </TableCell>
              <TableCell>
                <Label htmlFor={`watch-board-${i}`} className="sr-only">
                  Board {i + 1}
                </Label>
                <Input id={`watch-board-${i}`} value={row.board} onChange={(e) => setRow(i, { board: e.target.value })} placeholder="board slug" />
              </TableCell>
              <TableCell>
                <Button variant="ghost" size="icon" aria-label={`Remove row ${i + 1}`} onClick={() => removeRow(i)}>
                  <Trash2 className="size-4" aria-hidden />
                </Button>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      <div className="flex justify-between">
        <Button variant="outline" onClick={() => setRows((r) => [...r, { company: "", source: "greenhouse", board: "" }])}>
          Add row
        </Button>
        <Button onClick={save} disabled={put.isPending}>
          Save
        </Button>
      </div>
    </div>
  );
}
