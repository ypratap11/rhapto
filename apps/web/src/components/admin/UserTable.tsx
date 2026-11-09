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
// At phone width each row is a stacked, labelled card (as the History table is), so Failed, Last seen
// and Status are never hidden behind a sideways scroll. From sm up it is a normal table.
const CELL =
  "max-sm:flex max-sm:gap-3 max-sm:px-0 max-sm:py-0.5 max-sm:before:w-20 max-sm:before:shrink-0 max-sm:before:text-muted-foreground max-sm:before:content-[attr(data-label)]";

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
          <Table className="max-sm:block">
            <TableHeader className="max-sm:sr-only">
              <TableRow>
                <TableHead>User</TableHead>
                <TableHead>Runs</TableHead>
                <TableHead>Failed (7 days)</TableHead>
                <TableHead>Last seen</TableHead>
                <TableHead>Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody className="max-sm:block">
              {users.map((u) => (
                <TableRow key={u.id} className="max-sm:mb-2 max-sm:block max-sm:h-auto max-sm:rounded-lg max-sm:border max-sm:px-3 max-sm:py-2">
                  <TableCell className={`${CELL} sm:min-w-56 break-all whitespace-normal`} data-label="User">
                    <Link href={`/admin/users/${u.id}`} className="inline-flex min-h-11 items-center text-primary underline-offset-4 hover:underline">
                      {u.email}
                    </Link>
                  </TableCell>
                  <TableCell className={CELL} data-label="Runs">{runsOf(u.runs_used, u.runs_limit)}</TableCell>
                  <TableCell className={CELL} data-label="Failed">{u.failed_count}</TableCell>
                  <TableCell className={CELL} data-label="Last seen">{ago(u.last_seen_at)}</TableCell>
                  <TableCell className={CELL} data-label="Status">{u.blocked ? <Badge variant="destructive">Blocked</Badge> : <Badge variant="outline">Active</Badge>}</TableCell>
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
