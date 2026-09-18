import { CheckCircle2, Circle } from "lucide-react";
import Link from "next/link";
import type { DashboardChecklist } from "@/lib/api/queries";

type Row = {
  label: string;
  done: (c: DashboardChecklist) => boolean;
  detail: (c: DashboardChecklist) => string;
  href: string;
};

// Fixed order per spec §2: setup steps first, then the two "quality" checks, then preferences.
const ROWS: Row[] = [
  {
    label: "Resume template",
    done: (c) => c.resume_template,
    detail: (c) => (c.resume_template ? "Uploaded" : "Upload the resume Rhapto tunes"),
    href: "/profile?card=resume-template",
  },
  {
    label: "Contact and answers",
    done: (c) => c.contact_answers,
    detail: (c) => (c.contact_answers ? "Complete" : "Name, email, phone, location, links"),
    href: "/profile?card=answers",
  },
  {
    label: "Tracks",
    done: (c) => c.tracks,
    detail: (c) => (c.tracks ? "At least one track" : "Pick a field and a role"),
    href: "/profile?card=tracks",
  },
  {
    label: "Verified blocks",
    done: (c) => c.blocks_verified,
    detail: (c) => `${c.verified_blocks} of ${c.total_blocks} verified`,
    href: "/profile?card=blocks",
  },
  {
    label: "Guardrails",
    done: (c) => c.guardrails,
    detail: (c) => (c.guardrails ? "Set" : "Decide what Rhapto may never write"),
    href: "/profile?card=guardrails",
  },
  {
    label: "Location preferences",
    done: (c) => c.location_preferences,
    detail: (c) => (c.location_preferences ? "Set" : "Home, preferred areas, remote"),
    href: "/profile?card=location",
  },
];

/** Spec §2: six checks, each an "Edit" deep link into the Profile page's matching card. */
export function ProfileChecklist({ checklist }: { checklist: DashboardChecklist }) {
  return (
    <section aria-labelledby="checklist-heading" className="space-y-3 rounded-card border border-border bg-surface p-4 shadow-card">
      <h2 id="checklist-heading" className="font-sans text-base font-semibold">
        Profile checklist
      </h2>
      <ul className="space-y-2">
        {ROWS.map((row) => {
          const done = row.done(checklist);
          const Icon = done ? CheckCircle2 : Circle;
          return (
            <li key={row.label} data-done={done ? "true" : "false"} className="flex items-center justify-between gap-3">
              <div className="flex min-w-0 items-center gap-2">
                <Icon aria-hidden="true" className={`size-4 shrink-0 ${done ? "text-fit-high" : "text-muted-foreground"}`} />
                <div className="min-w-0">
                  <p className="text-sm font-medium">{row.label}</p>
                  <p className="truncate text-xs text-muted-foreground">{row.detail(checklist)}</p>
                </div>
              </div>
              <Link href={row.href} className="shrink-0 text-xs underline-offset-4 hover:underline">
                Edit
              </Link>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
