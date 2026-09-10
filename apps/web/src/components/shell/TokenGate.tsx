"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useSyncExternalStore } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { hasToken } from "@/lib/api/client";

function subscribe(onStoreChange: () => void): () => void {
  window.addEventListener("storage", onStoreChange);
  return () => window.removeEventListener("storage", onStoreChange);
}

function getServerSnapshot(): boolean {
  return false;
}

export function TokenGate({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const connected = useSyncExternalStore(subscribe, hasToken, getServerSnapshot);
  if (pathname === "/settings") return <>{children}</>;
  if (connected) return <>{children}</>;
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
      </CardContent>
    </Card>
  );
}
