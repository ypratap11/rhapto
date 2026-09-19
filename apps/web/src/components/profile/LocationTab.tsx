"use client";

import { useState } from "react";
import { toast } from "sonner";
import { ApiErrorBanner } from "@/components/shell/ApiErrorBanner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api/client";
import { useAnswers, usePutAnswers } from "@/lib/api/queries";
import { SwitchField } from "./fields";

/**
 * Dedicated editor for the three answers that drive location priority: `location_home`,
 * `location_preferred`, and `remote_ok`. These used to be edited as raw key/value rows in
 * AnswersTab, which meant a user had to know to type `location_home` as a literal key — and since
 * those keys are commonly absent (a fresh profile only has a free-text `location` answer), the
 * dashboard read as "not set" with no obvious way to set it.
 */
export function LocationTab() {
  const answers = useAnswers();
  if (answers.isLoading) return <Skeleton className="h-40 w-full" />;
  if (answers.error) return <ApiErrorBanner error={answers.error} />;
  // See AnswersTab: keyed by data identity so the editable copy is (re)initialized only when the
  // server data actually changes (e.g. after a save), not on every render — avoids syncing props
  // into state via an effect.
  return <LocationBody key={JSON.stringify(answers.data ?? {})} initial={answers.data ?? {}} />;
}

function LocationBody({ initial }: { initial: Record<string, string> }) {
  const put = usePutAnswers();
  const [home, setHome] = useState(initial.location_home ?? "");
  const [preferred, setPreferred] = useState(initial.location_preferred ?? "");
  const [remoteOk, setRemoteOk] = useState(initial.remote_ok === "yes");

  async function save() {
    // Preserve every other answer key (location, relocation, onsite_preference, name, email, …) —
    // PUT /api/v1/profile/answers replaces the whole map, there is no per-key patch.
    const next: Record<string, string> = {
      ...initial,
      location_home: home,
      location_preferred: preferred,
      remote_ok: remoteOk ? "yes" : "no",
    };
    try {
      await put.mutateAsync(next);
      toast.success("Saved location preferences. The queue will re-score by location tier.");
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Could not save location preferences");
    }
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        These three answers set Rhapto&rsquo;s location priority and re-score the job queue when you save. They are
        separate from the free-text <code className="font-mono text-xs">location</code> answer used on your resume
        header &mdash; that one is unaffected by this editor, so update both if they should say the same thing.
      </p>
      <div className="space-y-1">
        <Label htmlFor="location-home">Home location</Label>
        <Input id="location-home" value={home} onChange={(e) => setHome(e.target.value)} placeholder="e.g. Austin, TX" />
      </div>
      <div className="space-y-1">
        <Label htmlFor="location-preferred">Preferred areas (comma separated)</Label>
        <Input
          id="location-preferred"
          value={preferred}
          onChange={(e) => setPreferred(e.target.value)}
          placeholder="e.g. Austin, Dallas, Remote (US)"
        />
      </div>
      <SwitchField name="location-remote-ok" label="Open to remote" checked={remoteOk} onCheckedChange={setRemoteOk} />
      <div className="flex justify-end">
        <Button onClick={save} disabled={put.isPending}>
          Save
        </Button>
      </div>
    </div>
  );
}
