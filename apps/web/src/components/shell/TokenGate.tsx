"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useSyncExternalStore } from "react";
import { Landing } from "@/components/landing/Landing";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { hasToken, SAME_ORIGIN_DEPLOYMENT } from "@/lib/api/client";
import { useMe } from "@/lib/api/queries";

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

// Token-mode-only: in access mode there is no token to enter, so /settings there is just the
// LLM-key screen like any other authenticated page, and this bypass does not apply.
const PUBLIC_ROUTES = new Set(["/settings", "/about"]);

export function TokenGate({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const tokenPresent = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
  // Called unconditionally, per React's rules of hooks, but only consulted in the access-mode
  // branch below. In token mode this issues one background /me request that 401s until a token
  // is entered; that failure is inert here, exactly as an unused query result always is.
  const me = useMe();

  if (SAME_ORIGIN_DEPLOYMENT) {
    // access mode: Cloudflare authenticated this request at the edge before it reached Rhapto at
    // all; there is no bearer token to check. /me succeeding (this instance's own allowlist check
    // passed too) is what "signed in" means here.
    if (me.isPending) return null;
    if (me.isSuccess) return <>{children}</>;
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

  if (PUBLIC_ROUTES.has(pathname)) return <>{children}</>;
  if (tokenPresent === null) return null;
  if (tokenPresent) return <>{children}</>;
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
