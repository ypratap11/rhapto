"use client";

import { useState } from "react";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Input } from "@/components/ui/input";
import { useResetRuns } from "@/lib/admin/queries";

type Props = {
  userId: string;
  runsUsed: number;
  suggested: number | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

export function ResetRunsDialog({ userId, runsUsed, suggested, open, onOpenChange }: Props) {
  const initial = suggested === null ? runsUsed : Math.max(0, runsUsed - suggested);
  const [text, setText] = useState(String(initial));
  const reset = useResetRuns(userId);
  const value = text.trim() === "" ? Number.NaN : Number(text);
  const valid = Number.isInteger(value) && value >= 0 && value <= runsUsed && value !== runsUsed;

  async function submit() {
    if (!valid) return;
    try {
      await reset.mutateAsync(value);
      onOpenChange(false);
    } catch {
      // The sentence is shown from reset.error below.
    }
  }

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Reset free runs</AlertDialogTitle>
          <AlertDialogDescription>
            This person has used {runsUsed}. Give back up to {runsUsed} runs by lowering the number used.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <label className="flex flex-col gap-1.5 text-sm text-foreground">
          Runs used after the reset
          <Input type="number" inputMode="numeric" min={0} max={runsUsed} value={text} onChange={(e) => setText(e.target.value)} className="min-h-11" />
        </label>
        {reset.error ? <p role="alert" className="text-sm text-destructive">{reset.error.message}</p> : null}
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction disabled={!valid || reset.isPending} onClick={(e) => { e.preventDefault(); void submit(); }}>
            Reset
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
