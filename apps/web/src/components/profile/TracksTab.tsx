"use client";

import { useState } from "react";
import { toast } from "sonner";
import { ApiErrorBanner } from "@/components/shell/ApiErrorBanner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { ApiError } from "@/lib/api/client";
import { useBases, useDeleteTrack, usePutTrack, useTracks, type Track } from "@/lib/api/queries";
import { ID_RE, splitList, joinList } from "@/lib/profile-forms";
import { EntityTable } from "./EntityTable";
import { FieldPicker } from "./FieldPicker";

type TrackForm = { id: string; name: string; description: string; keywords: string; resume_base: string; min_fit: string };

function trackToForm(t: Track): TrackForm {
  return { id: t.id, name: t.name, description: t.description ?? "", keywords: joinList(t.keywords), resume_base: t.resume_base, min_fit: String(t.min_fit) };
}

const emptyTrackForm: TrackForm = { id: "", name: "", description: "", keywords: "", resume_base: "", min_fit: "50" };

function formToTrack(form: TrackForm): Track {
  const minFit = Number(form.min_fit);
  return {
    id: form.id.trim(),
    name: form.name.trim(),
    description: form.description.trim() ? form.description.trim() : null,
    keywords: splitList(form.keywords),
    resume_base: form.resume_base.trim(),
    min_fit: Number.isFinite(minFit) ? Math.min(100, Math.max(0, minFit)) : 50,
  };
}

function validateTrackForm(form: TrackForm): Record<string, string> {
  const errors: Record<string, string> = {};
  if (!ID_RE.test(form.id.trim())) errors.id = "Use lowercase letters, digits, and hyphens, starting with a letter or digit.";
  if (!form.name.trim()) errors.name = "Name is required.";
  if (!form.resume_base.trim()) errors.resume_base = "Pick a resume base.";
  const minFit = Number(form.min_fit);
  if (!Number.isFinite(minFit) || minFit < 0 || minFit > 100) errors.min_fit = "Enter a number between 0 and 100.";
  return errors;
}

export function TracksTab() {
  const tracks = useTracks();
  const bases = useBases();
  const put = usePutTrack();
  const remove = useDeleteTrack();
  const [form, setForm] = useState<TrackForm | null>(null);
  const [isNew, setIsNew] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [pickerOpen, setPickerOpen] = useState(false);

  function open(track: Track | null) {
    setErrors({});
    setIsNew(track === null);
    setForm(track ? trackToForm(track) : emptyTrackForm);
  }

  async function save() {
    if (!form) return;
    const v = validateTrackForm(form);
    setErrors(v);
    if (Object.keys(v).length) return;
    try {
      await put.mutateAsync(formToTrack(form));
      toast.success(`Saved ${form.id}`);
      setForm(null);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Could not save the track");
    }
  }

  if (tracks.isLoading) return <Skeleton className="h-40 w-full" />;
  if (tracks.error) return <ApiErrorBanner error={tracks.error} />;
  const set = (patch: Partial<TrackForm>) => setForm((f) => (f ? { ...f, ...patch } : f));
  const availableBases = bases.data ?? [];

  return (
    <div className="space-y-3">
      <div className="flex justify-end gap-2">
        <Button variant="outline" onClick={() => setPickerOpen(true)}>
          Pick a field and role
        </Button>
        <Button onClick={() => open(null)}>Add track</Button>
      </div>
      <EntityTable<Track>
        rows={tracks.data ?? []}
        getKey={(t) => t.id}
        getLabel={(t) => t.id}
        emptyText="No tracks yet. Import your profile or add a track."
        onEdit={open}
        onDelete={async (t) => {
          try {
            await remove.mutateAsync(t.id);
            toast.success(`Deleted ${t.id}`);
          } catch (e) {
            toast.error(e instanceof ApiError ? e.message : "Could not delete the track");
          }
        }}
        columns={[
          { key: "id", header: "Id", render: (t) => <span className="font-mono text-xs">{t.id}</span> },
          { key: "name", header: "Name", render: (t) => t.name },
          { key: "resume_base", header: "Base", render: (t) => t.resume_base },
          { key: "min_fit", header: "Min fit", render: (t) => t.min_fit },
        ]}
      />
      <Dialog open={form !== null} onOpenChange={(o) => !o && setForm(null)}>
        <DialogContent className="flex max-h-[85vh] flex-col overflow-hidden sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{isNew ? "New track" : `Edit ${form?.id}`}</DialogTitle>
          </DialogHeader>
          {form ? (
            <div className="min-h-0 flex-1 space-y-3 overflow-y-auto pr-1">
              <div className="space-y-1">
                <Label htmlFor="track-id">Id</Label>
                <Input id="track-id" value={form.id} onChange={(e) => set({ id: e.target.value })} disabled={!isNew} />
                {errors.id ? <p className="text-xs text-destructive">{errors.id}</p> : null}
              </div>
              <div className="space-y-1">
                <Label htmlFor="track-name">Name</Label>
                <Input id="track-name" value={form.name} onChange={(e) => set({ name: e.target.value })} />
                {errors.name ? <p className="text-xs text-destructive">{errors.name}</p> : null}
              </div>
              <div className="space-y-1">
                <Label htmlFor="track-description">Description</Label>
                <Textarea id="track-description" rows={3} value={form.description} onChange={(e) => set({ description: e.target.value })} />
              </div>
              <div className="space-y-1">
                <Label htmlFor="track-keywords">Keywords (comma separated)</Label>
                <Input id="track-keywords" value={form.keywords} onChange={(e) => set({ keywords: e.target.value })} />
              </div>
              <div className="space-y-1">
                <Label>Resume base</Label>
                {bases.isLoading ? (
                  <Skeleton className="h-8 w-full" />
                ) : bases.error ? (
                  <ApiErrorBanner error={bases.error} />
                ) : availableBases.length > 0 ? (
                  <Select value={form.resume_base || undefined} onValueChange={(v) => v && set({ resume_base: v })}>
                    <SelectTrigger aria-label="Resume base">
                      <SelectValue placeholder="Choose a base" />
                    </SelectTrigger>
                    <SelectContent>
                      {availableBases.map((b) => (
                        <SelectItem key={b.id} value={b.id}>
                          {b.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                ) : (
                  <Input aria-label="Resume base" value={form.resume_base} onChange={(e) => set({ resume_base: e.target.value })} placeholder="base id" />
                )}
                {errors.resume_base ? <p className="text-xs text-destructive">{errors.resume_base}</p> : null}
              </div>
              <div className="space-y-1">
                <Label htmlFor="track-min-fit">Min fit (0-100)</Label>
                <Input id="track-min-fit" type="number" min={0} max={100} value={form.min_fit} onChange={(e) => set({ min_fit: e.target.value })} />
                {errors.min_fit ? <p className="text-xs text-destructive">{errors.min_fit}</p> : null}
              </div>
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
      <FieldPicker open={pickerOpen} onOpenChange={setPickerOpen} />
    </div>
  );
}
