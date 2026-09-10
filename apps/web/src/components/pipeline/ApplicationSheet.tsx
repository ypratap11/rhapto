"use client";

import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Textarea } from "@/components/ui/textarea";
import { ApiError } from "@/lib/api/client";
import { useDeleteApplication, usePatchApplication, type ApplicationOut } from "@/lib/api/queries";
import { formatDate } from "@/lib/format";
import { APPLICATION_STATUSES, STATUS_LABEL } from "@/lib/status";

export function ApplicationSheet({
  application,
  open,
  onOpenChange,
}: {
  application: ApplicationOut | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      {application ? <SheetBody key={application.id} application={application} onOpenChange={onOpenChange} /> : null}
    </Sheet>
  );
}

function SheetBody({ application, onOpenChange }: { application: ApplicationOut; onOpenChange: (open: boolean) => void }) {
  const patch = usePatchApplication();
  const remove = useDeleteApplication();
  const [notes, setNotes] = useState(application.notes);

  async function save(body: { status?: string; notes?: string }) {
    try {
      await patch.mutateAsync({ id: application.id, body });
      toast.success("Saved");
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Could not save");
    }
  }

  return (
    <SheetContent className="w-[420px] space-y-5 overflow-y-auto">
      <SheetHeader>
        <SheetTitle>{application.job.company ?? "Application"}</SheetTitle>
        <p className="text-sm text-muted-foreground">{application.job.title}</p>
      </SheetHeader>
      <div className="space-y-1">
        <Label>Status</Label>
        <Select value={application.status} onValueChange={(status) => status && save({ status })}>
          <SelectTrigger aria-label="Status">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {APPLICATION_STATUSES.map((s) => (
              <SelectItem key={s} value={s}>
                {STATUS_LABEL[s]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="space-y-1">
        <Label htmlFor="notes">Notes</Label>
        <Textarea id="notes" rows={5} value={notes} onChange={(e) => setNotes(e.target.value)} />
        <Button size="sm" onClick={() => save({ notes })} disabled={patch.isPending}>
          Save notes
        </Button>
      </div>
      <div>
        <h3 className="mb-1 font-sans text-xs font-semibold uppercase tracking-wide text-muted-foreground">History</h3>
        <ol className="space-y-1 text-sm">
          {application.status_history.map((h, i) => (
            <li key={i} className="flex justify-between">
              <span>{STATUS_LABEL[h.status as keyof typeof STATUS_LABEL] ?? h.status}</span>
              <span className="font-mono text-xs text-muted-foreground">{formatDate(h.at)}</span>
            </li>
          ))}
        </ol>
      </div>
      <div className="flex items-center justify-between">
        {application.package_id ? (
          <Link href={`/jobs/${application.job.id}/packages/${application.package_id}`} className="text-sm text-accent underline">
            Open package
          </Link>
        ) : (
          <span />
        )}
        <AlertDialog>
          <AlertDialogTrigger render={<Button variant="ghost" size="sm" className="text-red-700" />}>Delete</AlertDialogTrigger>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Remove this application from the board?</AlertDialogTitle>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Cancel</AlertDialogCancel>
              <AlertDialogAction
                onClick={async () => {
                  try {
                    await remove.mutateAsync(application.id);
                    onOpenChange(false);
                    toast.success("Application removed");
                  } catch (e) {
                    toast.error(e instanceof ApiError ? e.message : "Could not remove the application");
                  }
                }}
              >
                Remove
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </div>
    </SheetContent>
  );
}
