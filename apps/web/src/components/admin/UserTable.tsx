"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useUserSearch } from "@/lib/admin/queries";
import { ago, runsOf } from "./format";

const DEBOUNCE_MS = 250;

export function UserTable() {
  // The term lives in component state only: it is never put in the URL.
  const [typed, setTyped] = useState("");
  const [term, setTerm] = useState("");
  useEffect(() => {
    const t = setTimeout(() => setTerm(typed.trim()), DEBOUNCE_MS);
    return () => clearTimeout(t);
  }, [typed]);

  const search = useUserSearch(term);
  const users = search.data?.pages.flatMap((p) => p.users) ?? [];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="font-heading text-lg">Users</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <Input type="search" role="searchbox" aria-label="Search by email" placeholder="Search by email" value={typed} onChange={(e) => setTyped(e.target.value)} className="min-h-11" />
        {search.isError ? <p className="text-sm text-destructive">Could not load users.</p> : null}
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>User</TableHead>
                <TableHead>Runs</TableHead>
                <TableHead>Failed (7 days)</TableHead>
                <TableHead>Last seen</TableHead>
                <TableHead>Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {users.map((u) => (
                <TableRow key={u.id}>
                  <TableCell className="min-w-56 break-all whitespace-normal">
                    <Link href={`/admin/users/${u.id}`} className="inline-flex min-h-11 items-center text-primary underline-offset-4 hover:underline">
                      {u.email}
                    </Link>
                  </TableCell>
                  <TableCell>{runsOf(u.runs_used, u.runs_limit)}</TableCell>
                  <TableCell>{u.failed_count}</TableCell>
                  <TableCell>{ago(u.last_seen_at)}</TableCell>
                  <TableCell>{u.blocked ? <Badge variant="destructive">Blocked</Badge> : <Badge variant="outline">Active</Badge>}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
        {search.isSuccess && users.length === 0 ? <p className="text-sm text-muted-foreground">No users match.</p> : null}
        {search.hasNextPage ? (
          <Button variant="outline" className="min-h-11 self-start" disabled={search.isFetchingNextPage} onClick={() => void search.fetchNextPage()}>
            Load more
          </Button>
        ) : null}
      </CardContent>
    </Card>
  );
}
