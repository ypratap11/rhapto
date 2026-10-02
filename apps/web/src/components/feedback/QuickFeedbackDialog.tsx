"use client";

import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ApiError } from "@/lib/api/client";
import { useSubmitFeedback } from "@/lib/api/queries";
import { type FeedbackQuickAnswers, type PageArea, TEXT_MAX } from "@/lib/feedback";
import { ChoiceGroup } from "./ChoiceGroup";
import { FeedbackNotice } from "./FeedbackNotice";



type Kind = FeedbackQuickAnswers["kind"];
const KINDS: ReadonlyArray<{ value: Kind; label: string }> = [
  { value: "bug", label: "Bug" },
  { value: "confusing", label: "Confusing" },
  { value: "idea", label: "Idea" },
  { value: "worked_well", label: "It worked well" },
];
const RATINGS = [1, 2, 3, 4, 5].map((n) => ({ value: n, label: String(n) }));

export type FeedbackTarget = { area: PageArea; job_id?: string; package_id?: string };

export function QuickFeedbackDialog({
  open,
  onOpenChange,
  target,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  target: FeedbackTarget;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[calc(100dvh-2rem)] overflow-y-auto sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Feedback on this page</DialogTitle>
          <DialogDescription>A bug, a confusing moment, an idea, or something that just worked.</DialogDescription>
        </DialogHeader>
        {/* Remounted on each open so a previous, closed attempt never leaks into the next one. */}
        <QuickForm key={open ? "open" : "closed"} target={target} onOpenChange={onOpenChange} />
      </DialogContent>
    </Dialog>
  );
}

function QuickForm({ target, onOpenChange }: { target: FeedbackTarget; onOpenChange: (open: boolean) => void }) {
  const submit = useSubmitFeedback();
  const [kind, setKind] = useState<Kind | null>(null);
  const [rating, setRating] = useState<number | null>(null);
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function send() {
    if (!kind) return;
    setError(null);
    const answers: FeedbackQuickAnswers = { kind };
    if (rating !== null) answers.rating = rating;
    if (text.trim()) answers.text = text.trim();
    try {
      await submit.mutateAsync({
        form: "quick",
        page_area: target.area,
        ...(target.job_id ? { job_id: target.job_id } : {}),
        ...(target.package_id ? { package_id: target.package_id } : {}),
        answers,
      });
      toast.success("Thanks — sent.");
      onOpenChange(false);
    } catch (e) {
      // The typed text stays in state: a failed send must never cost someone their words.
      setError(e instanceof ApiError ? e.message : "Could not send your feedback. Try again in a moment.");
    }
  }

  return (
    <form
      className="space-y-4"
      onSubmit={(e) => {
        e.preventDefault();
        void send();
      }}
    >
      <ChoiceGroup legend="Type" options={KINDS} value={kind} onChange={setKind} />
      <ChoiceGroup legend="Rating" options={RATINGS} value={rating} onChange={setRating} optional />
      <div className="space-y-1.5">
        <Label htmlFor="quick-feedback-text">What happened?</Label>
        <Textarea
          id="quick-feedback-text"
          rows={4}
          maxLength={TEXT_MAX}
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
        <p className="text-right text-xs text-muted-foreground">{`${text.length} / ${TEXT_MAX}`}</p>
      </div>
      <FeedbackNotice />
      {error ? (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      ) : null}
      <div className="flex flex-col-reverse gap-2 sm:flex-row sm:items-center sm:justify-between">
        <Link
          href="/feedback"
          onClick={() => onOpenChange(false)}
          className="text-sm text-muted-foreground underline hover:text-foreground"
        >
          Take the full survey
        </Link>
        <Button type="submit" disabled={!kind || submit.isPending}>
          {submit.isPending ? "Sending…" : "Send"}
        </Button>
      </div>
    </form>
  );
}
