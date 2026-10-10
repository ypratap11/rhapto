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
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { StatusControl } from "@/components/pipeline/StatusControl";
import { Textarea } from "@/components/ui/textarea";
import { ApiError } from "@/lib/api/client";
import { useDeleteApplication, usePatchApplication, type ApplicationOut } from "@/lib/api/queries";
import { formatDate } from "@/lib/format";
import { STATUS_LABEL, type ApplicationStatus } from "@/lib/status";

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

  async function saveNotes() {
    try {
      await patch.mutateAsync({ id: application.id, body: { notes } });
      toast.success("Saved");
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Could not save");
    }
  }

  return (
    <SheetContent className="space-y-5 overflow-y-auto data-[side=right]:w-full data-[side=right]:sm:w-[420px] data-[side=right]:sm:max-w-[420px]">
      <SheetHeader>
        <SheetTitle>{application.job.company ?? "Application"}</SheetTitle>
        <p className="text-sm text-muted-foreground">{application.job.title}</p>
      </SheetHeader>
      <div className="px-4">
        <StatusControl application={application} />
      </div>
      <div className="space-y-1 px-4">
        <Label htmlFor="notes">Notes</Label>
        <Textarea id="notes" rows={5} value={notes} onChange={(e) => setNotes(e.target.value)} />
        <Button size="sm" className="max-md:min-h-11" onClick={() => void saveNotes()} disabled={patch.isPending}>
          Save notes
        </Button>
      </div>
      <div className="px-4">
        <h3 className="mb-1 font-sans text-xs font-semibold uppercase tracking-wide text-muted-foreground">History</h3>
        <ol className="space-y-1 text-sm">
          {application.status_history.map((h, i) => (
            <li key={`${h.status}-${h.at}-${i}`} className="flex justify-between">
              <span>{STATUS_LABEL[h.status as ApplicationStatus] ?? h.status}</span>
              <span className="font-mono text-xs text-muted-foreground">{formatDate(h.at)}</span>
            </li>
          ))}
        </ol>
      </div>
      <div className="flex items-center justify-between px-4 pb-4">
        {application.package_id ? (
          <Link href={`/jobs/${application.job.id}/packages/${application.package_id}`} className="inline-flex min-h-11 items-center text-sm text-accent underline">
            Open the resume used
          </Link>
        ) : (
          <span />
        )}
        <AlertDialog>
          <AlertDialogTrigger render={<Button variant="ghost" size="sm" className="text-destructive max-md:min-h-11" />}>Delete</AlertDialogTrigger>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Remove this application?</AlertDialogTitle>
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
