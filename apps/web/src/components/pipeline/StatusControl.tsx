"use client";

import { useRef } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ApiError } from "@/lib/api/client";
import { usePatchApplication, type ApplicationOut } from "@/lib/api/queries";
import { CLOSED_REASONS, CLOSED_REASON_LABEL, PIPELINE_STATUSES, STATUS_LABEL, type ApplicationStatus, type ClosedReason } from "@/lib/status";

export function StatusControl({ application }: { application: ApplicationOut }) {
  const patch = usePatchApplication();
  const followUpRef = useRef<HTMLInputElement>(null);
  // The API returns a full ISO datetime ("2026-09-25T00:00:00Z"), but a native `<input type="date">`
  // only accepts exactly "YYYY-MM-DD" for its value/defaultValue — anything else is silently
  // rejected and the field renders blank. Slicing to the date portion is enough since the time
  // component is always midnight UTC for this field.
  const followUpValue = application.follow_up_at ? application.follow_up_at.slice(0, 10) : "";

  async function saveStatus(status: string) {
    try {
      await patch.mutateAsync({ id: application.id, body: { status } });
      const label = STATUS_LABEL[status as ApplicationStatus] ?? status;
      toast.success(`Moved to ${label}`);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Could not update the status");
    }
  }

  async function saveClosedReason(closed_reason: string) {
    try {
      await patch.mutateAsync({ id: application.id, body: { closed_reason } });
      const label = CLOSED_REASON_LABEL[closed_reason as ClosedReason] ?? closed_reason;
      toast.success(`Reason saved: ${label}`);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Could not save the reason");
    }
  }

  async function saveFollowUp() {
    const value = followUpRef.current?.value ?? "";
    try {
      await patch.mutateAsync({ id: application.id, body: { follow_up_at: value || null } });
      toast.success("Follow-up saved");
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Could not save the follow-up date");
    }
  }

  return (
    <div className="space-y-4 rounded-card border border-border bg-surface p-4 shadow-card">
      <div className="space-y-1">
        <Label htmlFor="status-select">Status</Label>
        <Select value={application.status} onValueChange={(value: string | null) => value && saveStatus(value)}>
          <SelectTrigger id="status-select" aria-label="Status" className="max-md:min-h-11">
            <SelectValue>{(v: string | null) => (v ? (STATUS_LABEL[v as ApplicationStatus] ?? v) : "")}</SelectValue>
          </SelectTrigger>
          <SelectContent>
            {PIPELINE_STATUSES.map((s) => (
              <SelectItem key={s} value={s}>
                {STATUS_LABEL[s]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {application.status === "closed" ? (
        <div className="space-y-1">
          <Label htmlFor="closed-reason-select">Closed reason</Label>
          {/* value is always a defined string (never undefined) so the Select stays controlled for
              its whole lifetime — Base UI warns if a Select flips from uncontrolled to controlled,
              which happens the moment a reason is first saved if this starts as `undefined`. */}
          <Select value={application.closed_reason ?? ""} onValueChange={(value: string | null) => value && saveClosedReason(value)}>
            <SelectTrigger id="closed-reason-select" aria-label="Closed reason" className="max-md:min-h-11">
              <SelectValue placeholder="Why?">
                {(v: string | null) => (v ? (CLOSED_REASON_LABEL[v as ClosedReason] ?? v) : "Why?")}
              </SelectValue>
            </SelectTrigger>
            <SelectContent>
              {CLOSED_REASONS.map((r) => (
                <SelectItem key={r} value={r}>
                  {CLOSED_REASON_LABEL[r]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      ) : null}

      <div className="space-y-1">
        <Label htmlFor="follow-up-date">Follow up on</Label>
        <div className="flex items-center gap-2">
          {/* Keyed on the stored value: an uncontrolled input's `defaultValue` only applies once, so
              a successful save (or any other external change to follow_up_at) must remount the
              input — via key, not an effect — rather than warn Base UI about a moving default. */}
          <Input key={followUpValue || "none"} id="follow-up-date" type="date" defaultValue={followUpValue} ref={followUpRef} />
          <Button type="button" size="sm" className="max-md:min-h-11" onClick={saveFollowUp} disabled={patch.isPending}>
            Save follow-up
          </Button>
        </div>
      </div>
    </div>
  );
}
