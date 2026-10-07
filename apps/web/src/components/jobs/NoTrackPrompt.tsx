import Link from "next/link";
import { buttonVariants } from "@/components/ui/button";

/** A user with no target role has nothing to rank against, so the list is just the newest jobs. Say so
 * instead of presenting an unranked list as if it were ranked (spec A2), and send them to the role
 * picker (the Tracks card on the Profile page). */
export function NoTrackPrompt() {
  return (
    <div data-slot="no-track-prompt" className="space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-card border border-border bg-surface-muted p-4">
        <p className="text-sm font-medium">Pick the role you want and we&rsquo;ll rank these for you</p>
        <Link href="/profile?card=tracks" className={buttonVariants({ size: "sm" })}>
          Pick a role
        </Link>
      </div>
      <p className="text-sm text-muted-foreground">Newest jobs, not ranked yet</p>
    </div>
  );
}
