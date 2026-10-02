"use client";

import { usePathname } from "next/navigation";
import { MessageSquarePlus } from "lucide-react";
import { useState } from "react";
import { useSignedIn } from "@/components/shell/TokenGate";
import { Button } from "@/components/ui/button";
import { useMe } from "@/lib/api/queries";
import { areaForPath, contextForPath, FEEDBACK_HIDDEN_ROUTES } from "@/lib/feedback";
import { type FeedbackTarget, QuickFeedbackDialog } from "./QuickFeedbackDialog";

export function FeedbackButton() {
  const pathname = usePathname();
  const signedIn = useSignedIn();
  // Exactly TokenGate's enable condition (shared via useSignedIn), so this can never fire /me from
  // the public landing page. Same query key, so on app routes it reuses TokenGate's cached /me.
  const me = useMe({ enabled: signedIn });
  const [open, setOpen] = useState(false);
  const [target, setTarget] = useState<FeedbackTarget>({ area: "other" });

  const path = pathname.length > 1 ? pathname.replace(/\/+$/, "") : pathname;
  if (!signedIn || !me.isSuccess || FEEDBACK_HIDDEN_ROUTES.has(path)) return null;

  return (
    <>
      <Button
        variant="ghost"
        size="sm"
        aria-label="Feedback on this page"
        title="Feedback on this page"
        className="text-muted-foreground hover:text-foreground"
        onClick={() => {
          // Area and context are fixed at open time, so navigating while the dialog is open cannot retag it.
          setTarget({ area: areaForPath(pathname), ...contextForPath(pathname) });
          setOpen(true);
        }}
      >
        <MessageSquarePlus aria-hidden />
        <span className="hidden sm:inline">Feedback</span>
      </Button>
      <QuickFeedbackDialog open={open} onOpenChange={setOpen} target={target} />
    </>
  );
}
