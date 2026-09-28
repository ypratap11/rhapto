"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { toast } from "sonner";
import { ApiErrorBanner } from "@/components/shell/ApiErrorBanner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { Textarea } from "@/components/ui/textarea";
import { ApiError } from "@/lib/api/client";
import { packageKeys, useBlocks, useDeleteBlock, usePutBlock, type Block } from "@/lib/api/queries";
import { datelessBlocks } from "@/lib/blocks";
import { BLOCK_TYPES, blockToForm, emptyBlockForm, formToBlock, validateBlockForm, type BlockForm } from "@/lib/profile-forms";
import { EntityTable } from "./EntityTable";
import { CheckboxField } from "./fields";

export function BlocksTab() {
  const blocks = useBlocks();
  const put = usePutBlock();
  const remove = useDeleteBlock();
  const queryClient = useQueryClient();
  const [form, setForm] = useState<BlockForm | null>(null);
  const [isNew, setIsNew] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [advancedOpen, setAdvancedOpen] = useState(false);

  // Inline "click to edit" state for the Period cell (spec item C). Only one row can be mid-edit
  // at a time; Escape cancels without saving, Enter/blur save. `editingOriginalPeriod` is captured
  // once, when the edit starts, so the no-op check below doesn't depend on a render-time snapshot
  // that might already be stale by the time the user commits.
  const [editingPeriodId, setEditingPeriodId] = useState<string | null>(null);
  const [periodDraft, setPeriodDraft] = useState("");
  const [editingOriginalPeriod, setEditingOriginalPeriod] = useState<string | null>(null);
  const skipPeriodBlurRef = useRef(false);

  // "N need a period" chip (spec item C): toggled on, the table shows only blocks with no period.
  const [showOnlyMissingPeriod, setShowOnlyMissingPeriod] = useState(false);

  // Per-block in-flight tracking for row-level mutations (Verified toggle, Period edit), so one
  // row's mutation doesn't disable every other row's toggle the way a single shared
  // `put.isPending` would.
  const [pendingIds, setPendingIds] = useState<Set<string>>(new Set());

  function readBlock(id: string): Block | undefined {
    // Prefer the query cache over `blocks.data`: `blocks.data` is this render's snapshot, which
    // can already be one mutation behind if two row edits happen in quick succession before a
    // background refetch lands. `patchBlock` below keeps the cache patched synchronously after
    // every successful write specifically so this stays current without waiting on that refetch.
    return queryClient.getQueryData<Block[]>(packageKeys.blocks)?.find((b) => b.id === id) ?? blocks.data?.find((b) => b.id === id);
  }

  /**
   * Applies `patch` on top of the freshest known copy of block `id` (never a block object closed
   * over at render time) and PUTs the result — the API only exposes a whole-block PUT, so this is
   * how a single-field edit avoids clobbering a field some other in-flight edit just changed.
   * After the PUT succeeds, the cache is patched immediately rather than waiting on the background
   * refetch `usePutBlock`'s `onSuccess` triggers, so a second edit fired right after this one still
   * reads a fresh base even before that refetch completes.
   */
  async function patchBlock(id: string, patch: Partial<Block>): Promise<Block> {
    const current = readBlock(id);
    if (!current) throw new Error(`${id} is no longer available — it may have just been deleted.`);
    const next: Block = { ...current, ...patch };
    setPendingIds((s) => new Set(s).add(id));
    try {
      await put.mutateAsync(next);
    } finally {
      setPendingIds((s) => {
        const rest = new Set(s);
        rest.delete(id);
        return rest;
      });
    }
    queryClient.setQueryData<Block[]>(packageKeys.blocks, (old) => old?.map((b) => (b.id === id ? next : b)));
    return next;
  }

  function open(block: Block | null) {
    setErrors({});
    setIsNew(block === null);
    setForm(block ? blockToForm(block) : emptyBlockForm);
    setAdvancedOpen(false);
  }

  async function save() {
    if (!form) return;
    const v = validateBlockForm(form);
    setErrors(v);
    if (Object.keys(v).length) return;
    try {
      await put.mutateAsync(formToBlock(form));
      toast.success(`Saved ${form.id}`);
      setForm(null);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Could not save the block");
    }
  }

  async function toggleVerified(id: string) {
    const current = readBlock(id);
    if (!current) {
      toast.error(`${id} is no longer available — it may have just been deleted.`);
      return;
    }
    const target = !current.verified;
    const previousVerified = current.verified;
    try {
      await patchBlock(id, { verified: target });
      toast.success(`${target ? "Verified" : "Unverified"} ${id}`, {
        duration: 8000,
        action: {
          label: "Undo",
          onClick: async () => {
            try {
              // Re-reads the current record inside patchBlock and flips only `verified` back — if
              // the user edited the Period (or anything else) on this block while the toast was up,
              // that edit survives; Undo does not re-PUT the old whole-object snapshot.
              await patchBlock(id, { verified: previousVerified });
            } catch (e) {
              toast.error(e instanceof ApiError ? e.message : "Could not undo the change");
            }
          },
        },
      });
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Could not update the block");
    }
  }

  function startEditingPeriod(block: Block) {
    setEditingPeriodId(block.id);
    setPeriodDraft(block.period ?? "");
    setEditingOriginalPeriod(block.period ?? null);
  }

  function cancelEditingPeriod() {
    skipPeriodBlurRef.current = true;
    setEditingPeriodId(null);
  }

  async function commitPeriod(id: string) {
    const period = periodDraft.trim() ? periodDraft.trim() : null;
    setEditingPeriodId(null);
    if (period === editingOriginalPeriod) return;
    try {
      await patchBlock(id, { period });
      toast.success(`Saved ${id}`);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Could not save the period");
    }
  }

  if (blocks.isLoading) return <Skeleton className="h-40 w-full" />;
  if (blocks.error) return <ApiErrorBanner error={blocks.error} />;
  const set = (patch: Partial<BlockForm>) => setForm((f) => (f ? { ...f, ...patch } : f));
  const field = (id: keyof BlockForm, label: string, autoFocus = false) => (
    <div className="space-y-1">
      <Label htmlFor={`block-${id}`}>{label}</Label>
      <Input id={`block-${id}`} autoFocus={autoFocus} value={String(form?.[id] ?? "")} onChange={(e) => set({ [id]: e.target.value } as Partial<BlockForm>)} disabled={id === "id" && !isNew} />
      {errors[id] ? <p className="text-xs text-destructive">{errors[id]}</p> : null}
    </div>
  );

  const allBlocks = blocks.data ?? [];
  // Shared with the API's `dateless_blocks` count via one definition; see lib/blocks.ts.
  const missingPeriod = datelessBlocks(allBlocks);
  const rows = showOnlyMissingPeriod ? missingPeriod : allBlocks;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        {missingPeriod.length > 0 ? (
          <Button
            type="button"
            variant="outline"
            size="sm"
            aria-pressed={showOnlyMissingPeriod}
            onClick={() => setShowOnlyMissingPeriod((v) => !v)}
            className={showOnlyMissingPeriod ? "border-primary text-primary" : undefined}
          >
            {missingPeriod.length} {missingPeriod.length === 1 ? "needs" : "need"} a period
          </Button>
        ) : (
          <span />
        )}
        <Button onClick={() => open(null)}>Add block</Button>
      </div>
      {showOnlyMissingPeriod && missingPeriod.length === 0 ? (
        <p className="text-sm text-muted-foreground">Every block has a period.</p>
      ) : null}
      <EntityTable<Block>
        rows={rows}
        getKey={(b) => b.id}
        getLabel={(b) => b.id}
        emptyText="No blocks yet. Import your profile or add a block."
        onEdit={open}
        onDelete={async (b) => {
          try {
            await remove.mutateAsync(b.id);
            toast.success(`Deleted ${b.id}`);
          } catch (e) {
            toast.error(e instanceof ApiError ? e.message : "Could not delete the block");
          }
        }}
        columns={[
          { key: "id", header: "Id", render: (b) => <span className="font-mono text-xs">{b.id}</span> },
          { key: "type", header: "Type", render: (b) => b.type },
          { key: "org", header: "Org / role", render: (b) => [b.org, b.role].filter(Boolean).join(" · ") },
          {
            key: "period",
            header: "Period",
            render: (b) =>
              editingPeriodId === b.id ? (
                <Input
                  autoFocus
                  aria-label={`Period ${b.id}`}
                  value={periodDraft}
                  onChange={(e) => setPeriodDraft(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      void commitPeriod(b.id);
                    } else if (e.key === "Escape") {
                      // Also stop propagation: this table lives inside ProfileSummaryCard's own
                      // Sheet, which closes itself on Escape via a bubbled/document-level keydown
                      // handler. Without this, cancelling the inline edit closes that outer sheet
                      // too — found by clicking through the real page, not caught by the RTL test
                      // (jsdom doesn't reproduce base-ui's document-level Escape listener).
                      e.preventDefault();
                      e.stopPropagation();
                      cancelEditingPeriod();
                    }
                  }}
                  onBlur={() => {
                    if (skipPeriodBlurRef.current) {
                      skipPeriodBlurRef.current = false;
                      return;
                    }
                    void commitPeriod(b.id);
                  }}
                  className="h-7 w-32"
                />
              ) : (
                <button
                  type="button"
                  aria-label={`Edit period for ${b.id}`}
                  onClick={() => startEditingPeriod(b)}
                  className="rounded-sm px-1 -mx-1 text-left hover:bg-muted focus-visible:outline focus-visible:outline-2 focus-visible:outline-ring"
                >
                  {b.period ?? <span className="text-muted-foreground">Add period</span>}
                </button>
              ),
          },
          {
            key: "verified",
            header: "Verified",
            render: (b) => (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                aria-pressed={b.verified}
                aria-label={`Toggle verified for ${b.id}`}
                onClick={() => void toggleVerified(b.id)}
                disabled={pendingIds.has(b.id)}
              >
                <StatusBadge tone={b.verified ? "high" : "muted"}>{b.verified ? "yes" : "no"}</StatusBadge>
              </Button>
            ),
          },
        ]}
      />
      <Dialog open={form !== null} onOpenChange={(o) => !o && setForm(null)}>
        <DialogContent className="flex max-h-[85vh] flex-col overflow-hidden sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>{isNew ? "New block" : `Edit ${form?.id}`}</DialogTitle>
          </DialogHeader>
          {form ? (
            <div className="min-h-0 flex-1 space-y-4 overflow-y-auto pr-1">
              <div className="space-y-1">
                <Label htmlFor="block-content">Content</Label>
                <Textarea id="block-content" autoFocus rows={6} value={form.content} onChange={(e) => set({ content: e.target.value })} />
                {errors.content ? <p className="text-xs text-destructive">{errors.content}</p> : null}
              </div>
              <div className="grid grid-cols-2 gap-3">
                <CheckboxField name="block-verified" label="Verified" checked={form.verified} onCheckedChange={(v) => set({ verified: v })} />
                <div className="space-y-1">
                  <Label htmlFor="block-metric">Metric (only used when verified)</Label>
                  <Input id="block-metric" value={form.metric} onChange={(e) => set({ metric: e.target.value })} />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                {field("id", "Id")}
                <div className="space-y-1">
                  <Label>Type</Label>
                  <Select value={form.type} onValueChange={(type) => type && set({ type })}>
                    <SelectTrigger aria-label="Type">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {BLOCK_TYPES.map((t) => (
                        <SelectItem key={t} value={t}>
                          {t}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                {field("org", "Organisation")}
                {field("role", "Role")}
                {field("period", "Period")}
              </div>
              <details className="rounded-md border border-border" open={advancedOpen} onToggle={(e) => setAdvancedOpen(e.currentTarget.open)}>
                <summary className="cursor-pointer select-none rounded-md px-3 py-2 text-sm font-medium">Advanced</summary>
                <div className="space-y-3 border-t border-border p-3">
                  {field("tags", "Tags (comma separated)")}
                  {field("attribution", "Attribution phrase")}
                  {field("exclude_when", "Exclude when context is (comma separated)")}
                  <CheckboxField name="block-concurrent" label="Concurrent with other roles" checked={form.concurrent} onCheckedChange={(v) => set({ concurrent: v })} />
                </div>
              </details>
            </div>
          ) : null}
          <DialogFooter>
            <Button variant="outline" onClick={() => setForm(null)}>
              Cancel
            </Button>
            <Button onClick={save} disabled={put.isPending}>
              Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
