"use client";

import { Bookmark } from "lucide-react";
import Link from "next/link";
import { useId, useState } from "react";
import { toast } from "sonner";
import { ApiErrorBanner } from "@/components/shell/ApiErrorBanner";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { Switch } from "@/components/ui/switch";
import { TableSkeleton } from "@/components/ui/table-skeleton";
import { ApiError } from "@/lib/api/client";
import { useDeleteSavedSearch, useSavedSearches, useUpdateSavedSearch, type SearchIn, type SearchOut } from "@/lib/api/queries";

const REMOTE_LABEL: Record<SearchOut["remote"], string> = {
  include: "Include remote",
  only: "Remote only",
  exclude: "Exclude remote",
};

type EditForm = { name: string; keywords: string; location: string; remote: SearchOut["remote"] };

function toForm(search: SearchOut): EditForm {
  return { name: search.name, keywords: search.keywords.join(", "), location: search.location ?? "", remote: search.remote };
}

/** A body that keeps every field a PUT would otherwise silently clear, changing only what the
 * caller asked to change. `SearchIn.query` isn't part of `SearchOut`, so it's simply left out. */
function bodyFor(search: SearchOut, patch: Partial<EditForm & { active: boolean }>): SearchIn {
  const form = { ...toForm(search), active: search.active, ...patch };
  return {
    active: form.active,
    name: form.name.trim() || search.name,
    keywords: form.keywords
      .split(",")
      .map((k) => k.trim())
      .filter(Boolean),
    location: form.location.trim() ? form.location.trim() : null,
    remote: form.remote,
  };
}

function message(e: unknown, fallback: string): string {
  return e instanceof ApiError ? e.message : fallback;
}

/** Every saved search as one row: name, its keywords/location/remote, a "from a track" badge when
 * `derived_from_track_id` is set, a Pause switch, and Edit (a Sheet) / Delete (an AlertDialog). */
export function SavedSearchesSection() {
  const searches = useSavedSearches();
  const update = useUpdateSavedSearch();
  const remove = useDeleteSavedSearch();
  const [editing, setEditing] = useState<SearchOut | null>(null);
  const [form, setForm] = useState<EditForm | null>(null);
  const [confirmId, setConfirmId] = useState<string | null>(null);
  const nameId = useId();
  const keywordsId = useId();
  const locationId = useId();

  // Same two-boolean shape used across this page's other sections (see SourcesSection): isPaused
  // covers the unreachable-API case that settles with isLoading false and error null; nothingToShow
  // only falls back to the skeleton/banner when there is no cached list left to show.
  const hasIssue = Boolean(searches.error) || searches.isPaused;
  const nothingToShow = !searches.data && hasIssue;
  const confirmSearch = searches.data?.find((s) => s.id === confirmId) ?? null;

  function openEdit(search: SearchOut) {
    setEditing(search);
    setForm(toForm(search));
  }

  function closeEdit() {
    setEditing(null);
    setForm(null);
  }

  async function togglePause(search: SearchOut, active: boolean) {
    try {
      await update.mutateAsync({ id: search.id, body: bodyFor(search, { active }) });
      toast.success(active ? `Resumed ${search.name}` : `Paused ${search.name}`);
    } catch (e) {
      toast.error(message(e, `Could not update ${search.name}`));
    }
  }

  async function saveEdit() {
    if (!editing || !form) return;
    try {
      await update.mutateAsync({ id: editing.id, body: bodyFor(editing, form) });
      toast.success(`Saved ${form.name.trim() || editing.name}`);
      closeEdit();
    } catch (e) {
      toast.error(message(e, `Could not save ${editing.name}`));
    }
  }

  async function confirmDelete() {
    if (!confirmSearch) return;
    try {
      await remove.mutateAsync(confirmSearch.id);
      toast.success(`Deleted ${confirmSearch.name}`);
    } catch (e) {
      toast.error(message(e, `Could not delete ${confirmSearch.name}`));
    } finally {
      // AlertDialogAction does not close the dialog by itself in this build — that's ours to do,
      // on both the success and failure path (a failure needs the alert visible underneath).
      setConfirmId(null);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Saved searches</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {hasIssue ? <ApiErrorBanner error={searches.error ?? "Can't reach Rhapto's API."} /> : null}
        {!searches.data ? (
          nothingToShow ? null : <TableSkeleton />
        ) : searches.data.length === 0 ? (
          <EmptyState
            icon={Bookmark}
            title="No saved searches yet"
            description="Save a search from the Jobs page to see it here."
            action={
              <Link href="/jobs" className={buttonVariants({ size: "sm" })}>
                Go to Jobs
              </Link>
            }
          />
        ) : (
          <ul className="space-y-2">
            {searches.data.map((search) => (
              <li key={search.id} className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border p-3">
                <div className="min-w-0 space-y-1">
                  <div className="flex items-center gap-2">
                    <p className="truncate text-sm font-medium">{search.name}</p>
                    {search.derived_from_track_id ? <StatusBadge tone="muted">from a track</StatusBadge> : null}
                  </div>
                  <p className="truncate text-xs text-muted-foreground">
                    {[search.keywords.length > 0 ? search.keywords.join(", ") : "Any keywords", search.location ?? "Anywhere", REMOTE_LABEL[search.remote]].join(
                      " · ",
                    )}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-3">
                  <label className="flex items-center gap-2 text-xs text-muted-foreground">
                    Active
                    <Switch
                      aria-label={`Active — ${search.name}`}
                      checked={search.active}
                      onCheckedChange={(checked) => void togglePause(search, checked === true)}
                      disabled={update.isPending}
                    />
                  </label>
                  <Button size="sm" variant="outline" onClick={() => openEdit(search)}>
                    Edit
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => setConfirmId(search.id)}>
                    Delete
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </CardContent>

      <Sheet open={editing !== null} onOpenChange={(open) => !open && closeEdit()}>
        <SheetContent className="w-[440px] space-y-4 overflow-y-auto">
          <SheetHeader>
            <SheetTitle>Edit {editing?.name}</SheetTitle>
          </SheetHeader>
          {form ? (
            <>
              <div className="space-y-1 px-4">
                <Label htmlFor={nameId}>Name</Label>
                <Input id={nameId} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
              </div>
              <div className="space-y-1 px-4">
                <Label htmlFor={keywordsId}>Keywords (comma separated)</Label>
                <Input id={keywordsId} value={form.keywords} onChange={(e) => setForm({ ...form, keywords: e.target.value })} />
              </div>
              <div className="space-y-1 px-4">
                <Label htmlFor={locationId}>Location</Label>
                <Input
                  id={locationId}
                  value={form.location}
                  onChange={(e) => setForm({ ...form, location: e.target.value })}
                  placeholder="Anywhere"
                />
              </div>
              <div className="space-y-1 px-4">
                <Label>Remote</Label>
                <Select value={form.remote} onValueChange={(v) => v && setForm({ ...form, remote: v as SearchOut["remote"] })}>
                  <SelectTrigger aria-label="Remote">
                    <SelectValue>{() => REMOTE_LABEL[form.remote]}</SelectValue>
                  </SelectTrigger>
                  <SelectContent>
                    {(Object.keys(REMOTE_LABEL) as SearchOut["remote"][]).map((r) => (
                      <SelectItem key={r} value={r}>
                        {REMOTE_LABEL[r]}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="flex justify-end gap-2 px-4">
                <Button variant="outline" onClick={closeEdit}>
                  Cancel
                </Button>
                <Button onClick={() => void saveEdit()} disabled={update.isPending}>
                  Save
                </Button>
              </div>
            </>
          ) : null}
        </SheetContent>
      </Sheet>

      <AlertDialog open={confirmId !== null} onOpenChange={(open) => !open && setConfirmId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete {confirmSearch?.name}?</AlertDialogTitle>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={() => void confirmDelete()} disabled={remove.isPending}>
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  );
}
