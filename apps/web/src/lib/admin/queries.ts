"use client";

import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, apiUrl, authHeaders, type Problem } from "@/lib/api/client";
import type { ActionResultOut, OverviewOut, ResetIn, UserDetailOut, UserSearchIn, UserSearchOut } from "./types";

/** The only place an admin path or method is written; routes.test.ts compares it to contract.json. */
export const ADMIN_ROUTES = {
  session: { method: "GET", path: "/admin/session" },
  overview: { method: "GET", path: "/admin/overview" },
  search: { method: "POST", path: "/admin/users/search" },
  user: { method: "GET", path: "/admin/users/{user_id}" },
  reset: { method: "POST", path: "/admin/users/{user_id}/reset-runs" },
  block: { method: "POST", path: "/admin/users/{user_id}/block" },
  unblock: { method: "POST", path: "/admin/users/{user_id}/unblock" },
} as const;

type Route = (typeof ADMIN_ROUTES)[keyof typeof ADMIN_ROUTES];

const PREFIX = "/api/v1";

function build(route: Route, userId?: string): string {
  return PREFIX + route.path.replace("{user_id}", encodeURIComponent(userId ?? ""));
}

/** Same error shape as lib/api/client.ts: a non-2xx becomes an ApiError carrying the problem body. */
async function adminFetch<T>(route: Route, opts: { userId?: string; body?: unknown } = {}): Promise<T> {
  const hasBody = opts.body !== undefined;
  const response = await fetch(apiUrl(build(route, opts.userId)), {
    method: route.method,
    headers: { ...authHeaders(), ...(hasBody ? { "Content-Type": "application/json" } : {}) },
    body: hasBody ? JSON.stringify(opts.body) : undefined,
    cache: "no-store",
  });
  if (response.ok) return (await response.json()) as T;
  let problem: Problem | null = null;
  try {
    const parsed: unknown = await response.json();
    if (parsed && typeof parsed === "object" && "status" in parsed) problem = parsed as Problem;
  } catch {
    problem = null;
  }
  throw new ApiError(response.status, problem, `HTTP ${response.status}`);
}

export const adminKeys = {
  overview: ["admin", "overview"] as const,
  users: ["admin", "users"] as const,
  user: (id: string) => ["admin", "user", id] as const,
};

export function useAdminOverview() {
  return useQuery({ queryKey: adminKeys.overview, queryFn: () => adminFetch<OverviewOut>(ADMIN_ROUTES.overview) });
}

/** The search term goes in the POST body, never in a URL. */
export function useUserSearch(q: string) {
  return useInfiniteQuery({
    queryKey: [...adminKeys.users, q],
    initialPageParam: 0,
    queryFn: ({ pageParam }) =>
      adminFetch<UserSearchOut>(ADMIN_ROUTES.search, { body: { q, offset: pageParam } satisfies UserSearchIn }),
    getNextPageParam: (last) => last.next_offset,
  });
}

export function useAdminUser(id: string) {
  return useQuery({ queryKey: adminKeys.user(id), queryFn: () => adminFetch<UserDetailOut>(ADMIN_ROUTES.user, { userId: id }) });
}

function useRefresh(id: string) {
  const qc = useQueryClient();
  return () =>
    Promise.all([
      qc.invalidateQueries({ queryKey: adminKeys.user(id) }),
      qc.invalidateQueries({ queryKey: adminKeys.users }),
      qc.invalidateQueries({ queryKey: adminKeys.overview }),
    ]);
}

export function useResetRuns(id: string) {
  const refresh = useRefresh(id);
  return useMutation({
    mutationFn: (to: number) => adminFetch<ActionResultOut>(ADMIN_ROUTES.reset, { userId: id, body: { to } satisfies ResetIn }),
    onSuccess: refresh,
  });
}

export function useSetBlocked(id: string) {
  const refresh = useRefresh(id);
  return useMutation({
    mutationFn: (blocked: boolean) =>
      adminFetch<ActionResultOut>(blocked ? ADMIN_ROUTES.block : ADMIN_ROUTES.unblock, { userId: id }),
    onSuccess: refresh,
  });
}
