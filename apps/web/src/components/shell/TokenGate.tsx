"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useSyncExternalStore } from "react";
import { Landing } from "@/components/landing/Landing";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ApiError, hasToken, SAME_ORIGIN_DEPLOYMENT } from "@/lib/api/client";
import { useBootstrap, useMe } from "@/lib/api/queries";

// Mounted only from the two "signed in, render children" branches below -- never on an
// unauthenticated landing page -- so this never fires the guaranteed-failing request I4 guarded
// against for /me. Fires the idempotent bootstrap exactly once per mount (guarded by
// `bootstrap.isIdle`, which also survives React StrictMode's dev-only double-invoke of effects);
// every call after the first (a re-mount, a second tab, an already-seeded account) is a cheap
// no-op on the server, so there's no cost to not trying to dedupe across sessions.
function Bootstrapper() {
  const bootstrap = useBootstrap();
  useEffect(() => {
    if (bootstrap.isIdle) {
      bootstrap.mutate();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- fire once on mount, not on every render
  }, []);
  return null;
}

function subscribe(onStoreChange: () => void): () => void {
  window.addEventListener("storage", onStoreChange);
  window.addEventListener("rhapto-settings", onStoreChange);
  return () => {
    window.removeEventListener("storage", onStoreChange);
    window.removeEventListener("rhapto-settings", onStoreChange);
  };
}

function getSnapshot(): boolean | null {
  return hasToken();
}

function getServerSnapshot(): boolean | null {
  return null;
}

// Reachable without being signed in, in *either* mode. /settings is where a token-mode user
// enters credentials, and it is also the one screen an access-mode user needs if this build ever
// ends up pointed at a token-mode API -- without this bypass applying there too, they would have
// no route off the refusal card below (fix-round finding I2: this used to be token-mode-only).
// It still renders the token-mode "API connection" card there in access mode
// (apps/web/src/app/settings/page.tsx) -- harmless, but this task does not hide it (fix-round
// finding M3 corrects only the previous, inaccurate version of this comment, not that card).
// /about is marketing copy that needs no session in either mode.
const PUBLIC_ROUTES = new Set(["/settings", "/about"]);

export function TokenGate({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const tokenPresent = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
  // Called unconditionally, per React's rules of hooks, but only consulted in the access-mode
  // branch below. `enabled` keeps it from actually firing in token mode until a token exists, so
  // an anonymous landing-page visit no longer issues a guaranteed-failing request against
  // whatever API URL happens to be configured (fix-round finding I4).
  const me = useMe({ enabled: SAME_ORIGIN_DEPLOYMENT || hasToken() });

  if (PUBLIC_ROUTES.has(pathname)) return <>{children}</>;

  if (SAME_ORIGIN_DEPLOYMENT) {
    // access mode: Cloudflare authenticated this request at the edge before it reached Rhapto at
    // all; there is no bearer token to check. /me succeeding (this instance's own allowlist check
    // passed too) is what "signed in" means here.
    if (me.isPending) return null;
    if (me.isSuccess)
      return (
        <>
          <Bootstrapper />
          {children}
        </>
      );
    const deniedByAllowlist = me.error instanceof ApiError && (me.error.status === 401 || me.error.status === 403);
    if (deniedByAllowlist) {
      return (
        <Card className="mx-auto max-w-md">
          <CardHeader>
            <CardTitle>Access refused</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm text-muted-foreground">
            <p>
              This Rhapto instance is invite-only. If you believe you should have access, ask the
              owner to add your email to the invite list.
            </p>
          </CardContent>
        </Card>
      );
    }
    // Any other failure -- a 500, a network blip, the API mid-restart -- is not a refusal and must
    // not be told to the person as one (fix-round finding I1: every non-success state used to
    // render "invite-only", including a merely-unreachable API).
    return (
      <Card className="mx-auto max-w-md">
        <CardHeader>
          <CardTitle>Could not reach Rhapto</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm text-muted-foreground">
          <p>Something went wrong reaching the API. This usually clears up on its own.</p>
          <Button variant="outline" onClick={() => void me.refetch()}>
            Retry
          </Button>
        </CardContent>
      </Card>
    );
  }

  if (tokenPresent === null) return null;
  if (tokenPresent)
    return (
      <>
        <Bootstrapper />
        {children}
      </>
    );
  // The root is the one route a stranger reaches without being sent there, so it answers "what is
  // this?" rather than demanding a bearer token. Every other route keeps the short Connect card:
  // someone who navigated to /jobs already knows what Rhapto is and just needs to be let in.
  if (pathname === "/") return <Landing />;
  return (
    <Card className="mx-auto max-w-md">
      <CardHeader>
        <CardTitle>Connect to your Rhapto API</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm text-muted-foreground">
        <p>
          Enter the API URL and the bearer token from your <code>.env</code> to start.
        </p>
        <Link href="/settings" className="text-accent underline">
          Open settings
        </Link>
        <p>
          New here?{" "}
          <Link href="/about" className="text-accent underline">
            See what Rhapto does
          </Link>{" "}
          first.
        </p>
      </CardContent>
    </Card>
  );
}
