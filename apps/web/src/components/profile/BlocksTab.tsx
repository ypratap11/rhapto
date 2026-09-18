"use client";

import { useState } from "react";
import { toast } from "sonner";
import { ApiErrorBanner } from "@/components/shell/ApiErrorBanner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { Textarea } from "@/components/ui/textarea";
import { ApiError } from "@/lib/api/client";
import { useBlocks, useDeleteBlock, usePutBlock, type Block } from "@/lib/api/queries";
import { BLOCK_TYPES, blockToForm, emptyBlockForm, formToBlock, validateBlockForm, type BlockForm } from "@/lib/profile-forms";
import { EntityTable } from "./EntityTable";
import { CheckboxField } from "./fields";

export function BlocksTab() {
  const blocks = useBlocks();
  const put = usePutBlock();
  const remove = useDeleteBlock();
  const [form, setForm] = useState<BlockForm | null>(null);
  const [isNew, setIsNew] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});

  function open(block: Block | null) {
    setErrors({});
    setIsNew(block === null);
    setForm(block ? blockToForm(block) : emptyBlockForm);
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

  if (blocks.isLoading) return <Skeleton className="h-40 w-full" />;
  if (blocks.error) return <ApiErrorBanner error={blocks.error} />;
  const set = (patch: Partial<BlockForm>) => setForm((f) => (f ? { ...f, ...patch } : f));
  const field = (id: keyof BlockForm, label: string, multiline = false) => (
    <div className="space-y-1">
      <Label htmlFor={`block-${id}`}>{label}</Label>
      {multiline ? (
        <Textarea id={`block-${id}`} rows={3} value={String(form?.[id] ?? "")} onChange={(e) => set({ [id]: e.target.value } as Partial<BlockForm>)} />
      ) : (
        <Input id={`block-${id}`} value={String(form?.[id] ?? "")} onChange={(e) => set({ [id]: e.target.value } as Partial<BlockForm>)} disabled={id === "id" && !isNew} />
      )}
      {errors[id] ? <p className="text-xs text-destructive">{errors[id]}</p> : null}
    </div>
  );

  return (
    <div className="space-y-3">
      <div className="flex justify-end">
        <Button onClick={() => open(null)}>Add block</Button>
      </div>
      <EntityTable<Block>
        rows={blocks.data ?? []}
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
          { key: "period", header: "Period", render: (b) => b.period ?? "" },
          { key: "verified", header: "Verified", render: (b) => <StatusBadge tone={b.verified ? "high" : "muted"}>{b.verified ? "yes" : "no"}</StatusBadge> },
        ]}
      />
      <Sheet open={form !== null} onOpenChange={(o) => !o && setForm(null)}>
        <SheetContent className="w-[480px] space-y-3 overflow-y-auto">
          <SheetHeader>
            <SheetTitle>{isNew ? "New block" : `Edit ${form?.id}`}</SheetTitle>
          </SheetHeader>
          {form ? (
            <>
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
              {field("content", "Content", true)}
              {field("metric", "Metric (only used when verified)")}
              <CheckboxField name="block-verified" label="Verified" checked={form.verified} onCheckedChange={(v) => set({ verified: v })} />
              <CheckboxField name="block-concurrent" label="Concurrent with other roles" checked={form.concurrent} onCheckedChange={(v) => set({ concurrent: v })} />
              {field("tags", "Tags (comma separated)")}
              {field("attribution", "Attribution phrase")}
              {field("exclude_when", "Exclude when context is (comma separated)")}
              <div className="flex justify-end gap-2">
                <Button variant="outline" onClick={() => setForm(null)}>
                  Cancel
                </Button>
                <Button onClick={save} disabled={put.isPending}>
                  Save
                </Button>
              </div>
            </>
          ) : null}
        </SheetContent>
      </Sheet>
    </div>
  );
}
