"use client";

import { X } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import type { DashboardChecklist } from "@/lib/api/queries";

const KEY = "rhapto.dashboard.setup-dismissed";
const REQUIRED = ["resume_template", "tracks"] as const;
const CARD = { resume_template: "/profile?card=resume-template", tracks: "/profile?card=tracks" } as const;

function dismissedBefore(): boolean {
  try {
    return window.localStorage.getItem(KEY) === "1";
  } catch {
    return false;
  }
}

/** At most one line, only while a required profile item is incomplete, and the person can dismiss it. */
export function FinishSetupLine({ checklist }: { checklist: DashboardChecklist | null | undefined }) {
  const [dismissed, setDismissed] = useState(dismissedBefore);
  if (!checklist || dismissed) return null;
  const missingKeys = REQUIRED.filter((k) => !checklist[k]);
  const missing = missingKeys.length;
  if (missing === 0) return null;
  // Exactly one thing missing: open that card, not the top of the profile.
  const href = missingKeys.length === 1 ? CARD[missingKeys[0]!] : "/profile";
  return (
    <div className="flex items-center justify-between gap-2 text-sm text-muted-foreground">
      <Link href={href} className="inline-flex min-h-11 items-center underline-offset-4 hover:text-foreground hover:underline">
        {missing === 1 ? "1 thing to finish in your profile ›" : `${missing} things to finish in your profile ›`}
      </Link>
      <button
        type="button"
        aria-label="Dismiss"
        className="inline-flex size-11 items-center justify-center rounded-control hover:bg-muted"
        onClick={() => {
          try {
            window.localStorage.setItem(KEY, "1");
          } catch {
            // not remembered; hidden for this visit
          }
          setDismissed(true);
        }}
      >
        <X className="size-4" aria-hidden />
      </button>
    </div>
  );
}
