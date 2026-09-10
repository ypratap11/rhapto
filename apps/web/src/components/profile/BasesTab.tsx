"use client";

import { useState } from "react";
import { toast } from "sonner";
import { ApiErrorBanner } from "@/components/shell/ApiErrorBanner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api/client";
import { useBases, useBlocks, useDeleteBase, usePutBase, type ResumeBase } from "@/lib/api/queries";
import { splitList, joinList } from "@/lib/profile-forms";
import { CheckboxField } from "./fields";
import { EntityTable } from "./EntityTable";

const DEFAULT_SECTION_ORDER = ["summary", "experience", "projects", "skills", "credentials"];

type BaseForm = { id: string; name: string; block_ids: string[]; section_order: string; style: Record<string, unknown> };

function baseToForm(base: ResumeBase): BaseForm {
  return { id: base.id, name: base.name, block_ids: base.block_ids, section_order: joinList(base.section_order), style: base.style };
}

const emptyBaseForm: BaseForm = { id: "", name: "", block_ids: [], section_order: joinList(DEFAULT_SECTION_ORDER), style: {} };

function formToBase(form: BaseForm): ResumeBase {
  const order = splitList(form.section_order);
  return {
    id: form.id.trim(),
    name: form.name.trim(),
    block_ids: form.block_ids,
    section_order: order.length ? order : DEFAULT_SECTION_ORDER,
    style: form.style,
  };
}

function validateBaseForm(form: BaseForm): Record<string, string> {
  const errors: Record<string, string> = {};
  if (!/^[a-z0-9][a-z0-9-]*$/.test(form.id.trim())) errors.id = "Use lowercase letters, digits, and hyphens, starting with a letter or digit.";
  if (!form.name.trim()) errors.name = "Name is required.";
  return errors;
}

export function BasesTab() {
  const bases = useBases();
  const blocks = useBlocks();
  const put = usePutBase();
  const remove = useDeleteBase();
  const [form, setForm] = useState<BaseForm | null>(null);
  const [isNew, setIsNew] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});

  function open(base: ResumeBase | null) {
    setErrors({});
    setIsNew(base === null);
    setForm(base ? baseToForm(base) : emptyBaseForm);
  }

  async function save() {
    if (!form) return;
    const v = validateBaseForm(form);
    setErrors(v);
    if (Object.keys(v).length) return;
    try {
      await put.mutateAsync(formToBase(form));
      toast.success(`Saved ${form.id}`);
      setForm(null);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Could not save the base");
    }
  }

  if (bases.isLoading) return <Skeleton className="h-40 w-full" />;
  if (bases.error) return <ApiErrorBanner error={bases.error} />;
  const set = (patch: Partial<BaseForm>) => setForm((f) => (f ? { ...f, ...patch } : f));
  const availableBlocks = blocks.data ?? [];

  function toggleBlock(blockId: string, checked: boolean) {
    set({ block_ids: checked ? [...(form?.block_ids ?? []), blockId] : (form?.block_ids ?? []).filter((id) => id !== blockId) });
  }

  return (
    <div className="space-y-3">
      <div className="flex justify-end">
        <Button onClick={() => open(null)}>Add base</Button>
      </div>
      <EntityTable<ResumeBase>
        rows={bases.data ?? []}
        getKey={(b) => b.id}
        getLabel={(b) => b.id}
        emptyText="No resume bases yet. Import your profile or add a base."
        onEdit={open}
        onDelete={async (b) => {
          await remove.mutateAsync(b.id);
          toast.success(`Deleted ${b.id}`);
        }}
        columns={[
          { key: "id", header: "Id", render: (b) => <span className="font-mono text-xs">{b.id}</span> },
          { key: "name", header: "Name", render: (b) => b.name },
          { key: "blocks", header: "Blocks", render: (b) => b.block_ids.length },
        ]}
      />
      <Sheet open={form !== null} onOpenChange={(o) => !o && setForm(null)}>
        <SheetContent className="w-[440px] space-y-3 overflow-y-auto">
          <SheetHeader>
            <SheetTitle>{isNew ? "New base" : `Edit ${form?.id}`}</SheetTitle>
          </SheetHeader>
          {form ? (
            <>
              <div className="space-y-1">
                <Label htmlFor="base-id">Id</Label>
                <Input id="base-id" value={form.id} onChange={(e) => set({ id: e.target.value })} disabled={!isNew} />
                {errors.id ? <p className="text-xs text-red-700">{errors.id}</p> : null}
              </div>
              <div className="space-y-1">
                <Label htmlFor="base-name">Name</Label>
                <Input id="base-name" value={form.name} onChange={(e) => set({ name: e.target.value })} />
                {errors.name ? <p className="text-xs text-red-700">{errors.name}</p> : null}
              </div>
              <div className="space-y-1">
                <Label htmlFor="base-section-order">Section order (comma separated)</Label>
                <Input id="base-section-order" value={form.section_order} onChange={(e) => set({ section_order: e.target.value })} />
              </div>
              <div className="space-y-1">
                <Label>Blocks</Label>
                <div className="max-h-64 space-y-1.5 overflow-y-auto rounded-md border p-2">
                  {availableBlocks.length === 0 ? <p className="text-xs text-muted-foreground">No blocks yet.</p> : null}
                  {availableBlocks.map((b) => (
                    <CheckboxField key={b.id} id={`base-block-${b.id}`} label={b.id} checked={form.block_ids.includes(b.id)} onCheckedChange={(checked) => toggleBlock(b.id, checked)} />
                  ))}
                </div>
              </div>
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
