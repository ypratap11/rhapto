"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useSyncExternalStore } from "react";
import { Landing } from "@/components/landing/Landing";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { hasToken } from "@/lib/api/client";

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

// Routes that render without a token. `/settings` is where the token is entered, so gating it
// would lock a new user out of the only screen that can unlock the rest; `/about` explains what
// Rhapto is, which is precisely what someone who has no token yet needs to read first.
const PUBLIC_ROUTES = new Set(["/settings", "/about"]);

export function TokenGate({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const connected = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
  if (PUBLIC_ROUTES.has(pathname)) return <>{children}</>;
  if (connected === null) return null;
  if (connected) return <>{children}</>;
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
