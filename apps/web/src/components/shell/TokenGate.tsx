"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useSyncExternalStore } from "react";
import { accessRequestLink } from "@/components/landing/access";
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
// This set is NOT the edge-bypass list -- it says "renders without a session", not "safe for the
// internet". /settings is a member of this set precisely because it stays gated at the edge (the
// runbook's bypass only ever adds /, /about, /_next/* and /favicon.ico, and
// scripts/check-access-boundary.sh asserts /settings stays protected); adding a route here grants
// it no edge exposure at all, only a client-side pass-through once a request already arrived.
const PUBLIC_ROUTES = new Set(["/", "/settings", "/about"]);

// The one definition of "this visitor is (or may be) signed in, so /me is worth asking": not on a
// public route, and either an access-mode deployment (the edge already authenticated the request) or
// a stored token. TokenGate and the shell feedback button both gate `useMe` on it, so the button can
// never re-introduce fix-round finding I1 -- a /me call from the public landing page.
export function useSignedIn(): boolean {
  const pathname = usePathname();
  const tokenPresent = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
  return !PUBLIC_ROUTES.has(pathname) && (SAME_ORIGIN_DEPLOYMENT || tokenPresent === true);
}

export function TokenGate({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const tokenPresent = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
  const signedIn = useSignedIn();
  // Called unconditionally, per React's rules of hooks, but only consulted in the access-mode
  // branch below, and only once past the public-route return (fix-round finding I1: `enabled` used
  // to stay live on / in access mode, so every view of the soon-to-be-world-readable landing page
  // fired a same-origin GET /api/v1/me that Cloudflare Access would answer with its login redirect
  // -- harmless, since the response was never rendered at /, but pointless, and for a signed-in
  // visitor it still reached `current_user`, which creates the account row as a side effect).
  // `enabled` also keeps it from firing in token mode until a token exists, so an anonymous
  // landing-page visit doesn't issue a guaranteed-failing request against whatever API URL happens
  // to be configured (fix-round finding I4). Reuses `tokenPresent` (the `useSyncExternalStore`
  // snapshot above) rather than calling `hasToken()` again here (fix-round finding N2) -- on a
  // client re-render after the token changes both would agree, so the only place they can diverge
  // is the SSR/hydration render, where `getServerSnapshot` fixes `tokenPresent` at `null` while
  // `hasToken()` would already see a stored token; that divergence is unobservable here because
  // `me` is read only inside the `SAME_ORIGIN_DEPLOYMENT` branch below, where `||` short-circuits
  // to `true` regardless of either value.
  const me = useMe({ enabled: signedIn });

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
      const access = accessRequestLink();
      return (
        <Card className="mx-auto max-w-md">
          <CardHeader>
            <CardTitle>Rhapto is invite-only right now</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm text-muted-foreground">
            <p>Your email is not on the invite list yet.</p>
            <p>
              <a href={access.href} target={access.external ? "_blank" : undefined} rel={access.external ? "noreferrer" : undefined} className="text-primary underline underline-offset-4">
                Request access
              </a>
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
