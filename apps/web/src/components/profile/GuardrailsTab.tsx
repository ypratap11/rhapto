"use client";

import { useState } from "react";
import { toast } from "sonner";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog";
import { ApiErrorBanner } from "@/components/shell/ApiErrorBanner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
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

/** The plain sentence each rule is shown as. Unlisted rules fall back to their stored name. */
const RULE_LABELS: Record<string, string> = {
  "no-unverified-metrics": "Numbers must come from your resume file or a confirmed item",
  "no-invented-entities": "No invented companies, schools or tools",
  "date-consistency": "Dates are consistent",
  attribution: "Shared work stays marked as shared",
  "visibility-context": "Items you marked to leave out stay out",
};

function ruleLabel(rule: string): string {
  return RULE_LABELS[rule] ?? rule;
}

/** This rule always runs. It stays selectable so an existing saved setting can still be edited,
 * but it is never offered as a switch. */
const ALWAYS_ON = "no-unverified-metrics";

/** Rules where turning the switch off has a real, easy-to-miss consequence for output quality. */
const DEACTIVATION_WARNINGS: Record<string, string> = {
  "no-invented-entities": "Turning this off allows companies, schools and tools that are not in Your experience.",
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
      toast.success(`Saved: ${ruleLabel(form.rule)}`);
      setForm(null);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Could not save the rule");
    }
  }

  if (guardrails.isLoading) return <Skeleton className="h-40 w-full" />;
  if (guardrails.error) return <ApiErrorBanner error={guardrails.error} />;
  const set = (patch: Partial<GuardrailForm>) => setForm((f) => (f ? { ...f, ...patch } : f));

  return (
    <div className="space-y-3">
      <div className="flex justify-end">
        <Button onClick={() => open(null)}>Add a check</Button>
      </div>
      <EntityTable<GuardrailRule>
        rows={guardrails.data ?? []}
        getKey={(r) => r.rule}
        getLabel={(r) => ruleLabel(r.rule)}
        emptyText="No extra checks added. The standard rules apply."
        onEdit={open}
        onDelete={async (r) => {
          try {
            await remove.mutateAsync(r.rule);
            toast.success(`Deleted: ${ruleLabel(r.rule)}`);
          } catch (e) {
            toast.error(e instanceof ApiError ? e.message : "Could not delete the rule");
          }
        }}
        columns={[
          { key: "rule", header: "Rule", render: (r) => ruleLabel(r.rule) },
          {
            key: "active",
            header: "Status",
            render: (r) =>
              r.rule === ALWAYS_ON ? (
                <span className="text-sm">Always on</span>
              ) : (
                <StatusBadge tone={r.active ? "high" : "muted"}>{r.active ? "on" : "off"}</StatusBadge>
              ),
          },
        ]}
      />
      <Dialog open={form !== null} onOpenChange={(o) => !o && setForm(null)}>
        <DialogContent className="flex max-h-[85vh] flex-col overflow-hidden sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{isNew ? "New check" : `Edit: ${form ? ruleLabel(form.rule) : ""}`}</DialogTitle>
          </DialogHeader>
          {form ? (
            <div className="min-h-0 flex-1 space-y-3 overflow-y-auto pr-1">
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
                          {ruleLabel(r)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                ) : (
                  <p className="text-sm">{ruleLabel(form.rule)}</p>
                )}
              </div>
              <div className="space-y-1">
                {form.rule === ALWAYS_ON ? (
                  <p className="text-sm font-medium">Always on</p>
                ) : (
                  <SwitchField name="guardrail-active" label="Active" checked={form.active} onCheckedChange={requestActiveChange} />
                )}
                {form.rule !== ALWAYS_ON && DEACTIVATION_WARNINGS[form.rule] ? <p className="text-xs text-fit-mid">{DEACTIVATION_WARNINGS[form.rule]}</p> : null}
              </div>
              <details className="rounded-md border border-border" open={Boolean(errors.config) || form.config.trim().length > 0}>
                <summary className="cursor-pointer select-none rounded-md px-3 py-2 text-sm font-medium">Advanced</summary>
                <div className="space-y-1 border-t border-border p-3">
                  <Label htmlFor="guardrail-config">Extra settings (JSON object)</Label>
                  <Textarea id="guardrail-config" rows={6} value={form.config} onChange={(e) => set({ config: e.target.value })} placeholder="{}" />
                  {errors.config ? <p className="text-xs text-destructive">{errors.config}</p> : null}
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
      <AlertDialog open={confirmDeactivate} onOpenChange={(o) => !o && setConfirmDeactivate(false)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Turn off: {form ? ruleLabel(form.rule) : ""}?</AlertDialogTitle>
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
