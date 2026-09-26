"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useSyncExternalStore } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ApiError, hasToken, SAME_ORIGIN_DEPLOYMENT } from "@/lib/api/client";
import { useBootstrap, useMe } from "@/lib/api/queries";

// Fix-round M1: a `sessionStorage` latch, not `bootstrap.isIdle` alone -- `isIdle` only protects a
// single mount's effect running twice (see M2 below), but a signed-in user navigating through
// /settings or /about (both bypass Bootstrapper) and back to /jobs unmounts and remounts this
// component, and `isIdle` on a *fresh* `useBootstrap()` call is `true` again on every remount. The
// latch is set synchronously before the request even resolves, so a session where the request
// never actually completes (a network blip) does not retry until the next tab/session -- accepted
// as the cost of "once per session" being literally true; the server-side atomic claim is what
// actually protects the backfill itself, so a missed attempt just means one fewer cheap retry, not
// a correctness gap.
const BOOTSTRAP_ATTEMPTED_KEY = "rhapto.bootstrap-attempted";

function alreadyAttemptedBootstrap(): boolean {
  try {
    return sessionStorage.getItem(BOOTSTRAP_ATTEMPTED_KEY) === "1";
  } catch {
    // Private browsing / blocked storage: treat every mount as a fresh attempt. Each extra call is
    // one cheap UPDATE + ROLLBACK on the server (the atomic claim), never a duplicated backfill.
    return false;
  }
}

function markBootstrapAttempted(): void {
  try {
    sessionStorage.setItem(BOOTSTRAP_ATTEMPTED_KEY, "1");
  } catch {
    // ignore -- see alreadyAttemptedBootstrap
  }
}

// Mounted only from the two "signed in, render children" branches below -- never on an
// unauthenticated landing page -- so this never fires the guaranteed-failing request I4 guarded
// against for /me. Fix-round M2: the latch is set *synchronously* inside the effect, before
// `bootstrap.mutate()` is even called, so React StrictMode's dev-only mount -> cleanup -> remount
// double-invoke also only fires once -- the second invoke's `alreadyAttemptedBootstrap()` check
// already sees the flag the first invoke set (this is not `bootstrap.isIdle`, which is read from
// the render closure and would see `true` on both invokes).
function Bootstrapper() {
  const bootstrap = useBootstrap();
  useEffect(() => {
    if (!alreadyAttemptedBootstrap()) {
      markBootstrapAttempted();
      bootstrap.mutate();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- fire once per mount, not on every render
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
// The token-mode "API connection" card that used to render unconditionally on /settings is now
// hidden in access mode (apps/web/src/app/settings/page.tsx, fix-round finding N1) because saving
// it there points the browser at another origin and silently disables the same-origin proxy.
// /about is marketing copy that needs no session in either mode, and neither does / -- it is the
// domain's front door (apps/web/src/app/page.tsx renders <Landing/> there directly), so it must
// render the same way for a first-time invited person as for anyone already signed in. This is a
// client-side routing choice, not a claim that / is reachable by anyone unauthenticated: in an
// access-mode deployment, Cloudflare Access still stops a stranger at the edge before this code
// ever runs, unless a separate, deliberate step (docs/runbook-public-landing.md) opens / there too.
const PUBLIC_ROUTES = new Set(["/", "/settings", "/about"]);

export function TokenGate({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const tokenPresent = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
  // Called unconditionally, per React's rules of hooks, but only consulted in the access-mode
  // branch below. `enabled` keeps it from actually firing in token mode until a token exists, so
  // an anonymous landing-page visit no longer issues a guaranteed-failing request against
  // whatever API URL happens to be configured (fix-round finding I4). Reuses `tokenPresent` (the
  // `useSyncExternalStore` snapshot above) rather than calling `hasToken()` again here -- same
  // value, one source of truth, and it re-renders correctly when the token changes (fix-round
  // finding N2: a fresh `hasToken()` call during render doesn't react to that change on its own).
  const me = useMe({ enabled: SAME_ORIGIN_DEPLOYMENT || tokenPresent === true });

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
  // / is handled above by PUBLIC_ROUTES, so every route that reaches here (/jobs, /pipeline, ...)
  // is one someone navigated to directly, without a token -- they already know what Rhapto is and
  // just need to be let in, so the short Connect card is enough.
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
