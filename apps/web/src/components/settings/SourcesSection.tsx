"use client";

import { useRef } from "react";
import { toast } from "sonner";
import { ApiErrorBanner } from "@/components/shell/ApiErrorBanner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { TableSkeleton } from "@/components/ui/table-skeleton";
import { ApiError } from "@/lib/api/client";
import { useSaveSourceSettings, useSourceSettings, useTestSource, type SourceSetting } from "@/lib/api/queries";

function statusLine(s: SourceSetting): string {
  if (!s.needs_key) return "Zero setup";
  return s.key_set ? "Key saved" : "Needs a key";
}

function message(e: unknown, fallback: string): string {
  return e instanceof ApiError ? e.message : fallback;
}

/** One `<fieldset role="group">` per configured job source: an enable switch that saves the
 * instant it's flipped, masked (never-prefilled) key fields a separate Save posts as
 * `credentials`, and — where the API offers it — a Test button. Key fields are read through refs
 * on Save rather than mirrored into React state, so a typed key exists in the DOM only until it is
 * sent, never in a value this component could re-render, log, or leave sitting around. */
export function SourcesSection() {
  const sources = useSourceSettings();
  const save = useSaveSourceSettings();
  const test = useTestSource();
  const fieldRefs = useRef(new Map<string, HTMLInputElement>());

  // Same shape as every other query on this page (see resumes/page.tsx, pipeline/page.tsx): a
  // paused fetch (API unreachable) settles with isLoading false and error null, so isPaused is
  // checked explicitly. hasIssue shows the banner even alongside stale cached rows; nothingToShow
  // only gates falling back to the skeleton/banner when there is truly nothing cached to render.
  const hasIssue = Boolean(sources.error) || sources.isPaused;
  const nothingToShow = !sources.data && hasIssue;

  async function toggle(source: SourceSetting) {
    try {
      await save.mutateAsync({ source: source.id, body: { enabled: !source.enabled } });
      toast.success(`${source.label} ${source.enabled ? "disabled" : "enabled"}`);
    } catch (e) {
      toast.error(message(e, `Could not update ${source.label}`));
    }
  }

  async function saveKeys(source: SourceSetting) {
    const credentials: Record<string, string> = {};
    for (const field of source.fields) {
      const value = fieldRefs.current.get(`${source.id}:${field}`)?.value.trim() ?? "";
      if (value) credentials[field] = value;
    }
    try {
      await save.mutateAsync({
        source: source.id,
        body: { enabled: source.enabled, ...(Object.keys(credentials).length > 0 ? { credentials } : {}) },
      });
      for (const field of source.fields) {
        const input = fieldRefs.current.get(`${source.id}:${field}`);
        if (input) input.value = "";
      }
      toast.success(`Saved ${source.label}`);
    } catch (e) {
      toast.error(message(e, `Could not save ${source.label}`));
    }
  }

  async function runTest(source: SourceSetting) {
    try {
      const result = await test.mutateAsync(source.id);
      if (result.ok) toast.success(`Found ${result.found ?? 0} result(s)`);
      else toast.error(result.error ?? `Could not reach ${source.label}`);
    } catch (e) {
      toast.error(message(e, `Could not reach ${source.label}`));
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Job sources</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {hasIssue ? <ApiErrorBanner error={sources.error ?? "Can't reach Rhapto's API."} /> : null}
        {!sources.data ? (
          nothingToShow ? null : <TableSkeleton />
        ) : (
          sources.data.map((source) => (
            <fieldset key={source.id} role="group" aria-label={source.label} className="space-y-3 rounded-lg border border-border p-3">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-sm font-medium">{source.label}</p>
                  <p className="text-xs text-muted-foreground">{statusLine(source)}</p>
                </div>
                <Switch aria-label={source.label} checked={source.enabled} onCheckedChange={() => void toggle(source)} disabled={save.isPending} />
              </div>
              {source.fields.length > 0 ? (
                <div className="space-y-2">
                  {source.fields.map((field) => (
                    <div key={field} className="space-y-1">
                      <Label htmlFor={`${source.id}-${field}`}>{field}</Label>
                      <Input
                        id={`${source.id}-${field}`}
                        type="password"
                        autoComplete="off"
                        defaultValue=""
                        placeholder={source.key_set ? "Saved — enter a new value to replace it" : "Paste the key"}
                        ref={(el) => {
                          const key = `${source.id}:${field}`;
                          if (el) fieldRefs.current.set(key, el);
                          else fieldRefs.current.delete(key);
                        }}
                      />
                    </div>
                  ))}
                  <div className="flex gap-2">
                    <Button size="sm" onClick={() => void saveKeys(source)} disabled={save.isPending}>
                      Save
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => void runTest(source)} disabled={test.isPending}>
                      Test
                    </Button>
                  </div>
                </div>
              ) : (
                <Button size="sm" variant="outline" onClick={() => void runTest(source)} disabled={test.isPending}>
                  Test
                </Button>
              )}
            </fieldset>
          ))
        )}
      </CardContent>
    </Card>
  );
}
