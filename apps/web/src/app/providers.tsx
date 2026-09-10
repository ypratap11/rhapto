"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { Toaster } from "@/components/ui/sonner";
import { ApiError } from "@/lib/api/client";

function shouldRetry(failureCount: number, error: unknown): boolean {
  if (error instanceof ApiError && error.status >= 400 && error.status < 500) return false;
  return failureCount < 1;
}

export function Providers({ children }: { children: React.ReactNode }) {
  const [client] = useState(() => new QueryClient({ defaultOptions: { queries: { retry: shouldRetry, staleTime: 5_000 } } }));
  return (
    <QueryClientProvider client={client}>
      {children}
      <Toaster richColors position="bottom-right" />
    </QueryClientProvider>
  );
}
