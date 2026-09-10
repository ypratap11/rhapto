"use client";

import { useState } from "react";
import { toast } from "sonner";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog";
import { ApiErrorBanner } from "@/components/shell/ApiErrorBanner";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { Textarea } from "@/components/ui/textarea";
import { ApiError } from "@/lib/api/client";
import { useDeleteGuardrail, useGuardrails, usePutGuardrail, type GuardrailRule } from "@/lib/api/queries";
import { KNOWN_RULES, parseJsonObject } from "@/lib/profile-forms";
import { EntityTable } from "./EntityTable";
import { SwitchField } from "./fields";

type GuardrailForm = { rule: string; active: boolean; config: string };

function guardrailToForm(rule: GuardrailRule): GuardrailForm {
  return { rule: rule.rule, active: rule.active, config: Object.keys(rule.config).length ? JSON.stringify(rule.config, null, 2) : "" };
}

const emptyGuardrailForm: GuardrailForm = { rule: KNOWN_RULES[0], active: true, config: "" };

/** Rules where turning the switch off has a real, easy-to-miss consequence for output quality. */
const DEACTIVATION_WARNINGS: Record<string, string> = {
  "no-unverified-metrics": "Turning this off allows numbers that no verified block supports.",
  "no-invented-entities": "Turning this off allows employers, products, and tools that are not in your blocks.",
};

export function GuardrailsTab() {
  const guardrails = useGuardrails();
  const put = usePutGuardrail();
  const remove = useDeleteGuardrail();
  const [form, setForm] = useState<GuardrailForm | null>(null);
  const [isNew, setIsNew] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [confirmDeactivate, setConfirmDeactivate] = useState(false);

  function open(rule: GuardrailRule | null) {
    setErrors({});
    setIsNew(rule === null);
    setForm(rule ? guardrailToForm(rule) : emptyGuardrailForm);
    setConfirmDeactivate(false);
  }

  function requestActiveChange(next: boolean) {
    if (!next && form && DEACTIVATION_WARNINGS[form.rule]) {
      setConfirmDeactivate(true);
      return;
    }
    set({ active: next });
  }

  async function save() {
    if (!form) return;
    const { value, error } = parseJsonObject(form.config);
    if (error || value === null) {
      setErrors({ config: error ?? "Config must be a JSON object." });
      return;
    }
    setErrors({});
    try {
      await put.mutateAsync({ rule: form.rule, active: form.active, config: value });
      toast.success(`Saved ${form.rule}`);
      setForm(null);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Could not save the guardrail");
    }
  }

  if (guardrails.isLoading) return <Skeleton className="h-40 w-full" />;
  if (guardrails.error) return <ApiErrorBanner error={guardrails.error} />;
  const set = (patch: Partial<GuardrailForm>) => setForm((f) => (f ? { ...f, ...patch } : f));

  return (
    <div className="space-y-3">
      <div className="flex justify-end">
        <Button onClick={() => open(null)}>Add guardrail</Button>
      </div>
      <EntityTable<GuardrailRule>
        rows={guardrails.data ?? []}
        getKey={(r) => r.rule}
        getLabel={(r) => r.rule}
        emptyText="No guardrail overrides yet. Defaults apply until you add one."
        onEdit={open}
        onDelete={async (r) => {
          try {
            await remove.mutateAsync(r.rule);
            toast.success(`Deleted ${r.rule}`);
          } catch (e) {
            toast.error(e instanceof ApiError ? e.message : "Could not delete the guardrail");
          }
        }}
        columns={[
          { key: "rule", header: "Rule", render: (r) => <span className="font-mono text-xs">{r.rule}</span> },
          { key: "active", header: "Active", render: (r) => <StatusBadge tone={r.active ? "green" : "zinc"}>{r.active ? "yes" : "no"}</StatusBadge> },
          { key: "config", header: "Config", render: (r) => (Object.keys(r.config).length ? <span className="font-mono text-xs">{JSON.stringify(r.config)}</span> : <span className="text-muted-foreground">—</span>) },
        ]}
      />
      <Sheet open={form !== null} onOpenChange={(o) => !o && setForm(null)}>
        <SheetContent className="w-[440px] space-y-3 overflow-y-auto">
          <SheetHeader>
            <SheetTitle>{isNew ? "New guardrail override" : `Edit ${form?.rule}`}</SheetTitle>
          </SheetHeader>
          {form ? (
            <>
              <div className="space-y-1">
                <Label>Rule</Label>
                {isNew ? (
                  <Select value={form.rule} onValueChange={(v) => v && set({ rule: v })}>
                    <SelectTrigger aria-label="Rule">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {KNOWN_RULES.map((r) => (
                        <SelectItem key={r} value={r}>
                          {r}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                ) : (
                  <p className="font-mono text-sm">{form.rule}</p>
                )}
              </div>
              <div className="space-y-1">
                <SwitchField name="guardrail-active" label="Active" checked={form.active} onCheckedChange={requestActiveChange} />
                {DEACTIVATION_WARNINGS[form.rule] ? <p className="text-xs text-amber-700">{DEACTIVATION_WARNINGS[form.rule]}</p> : null}
              </div>
              <div className="space-y-1">
                <Label htmlFor="guardrail-config">Config (JSON object)</Label>
                <Textarea id="guardrail-config" rows={6} value={form.config} onChange={(e) => set({ config: e.target.value })} placeholder="{}" />
                {errors.config ? <p className="text-xs text-red-700">{errors.config}</p> : null}
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
      <AlertDialog open={confirmDeactivate} onOpenChange={(o) => !o && setConfirmDeactivate(false)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Turn off {form?.rule}?</AlertDialogTitle>
            <AlertDialogDescription>{form ? DEACTIVATION_WARNINGS[form.rule] : ""}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                set({ active: false });
                setConfirmDeactivate(false);
              }}
            >
              Turn off
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
