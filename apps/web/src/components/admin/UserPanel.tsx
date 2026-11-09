"use client";

import { useState } from "react";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ApiError } from "@/lib/api/client";
import { useAdminUser, useSetBlocked } from "@/lib/admin/queries";
import { actionWord, changeWords, dateOnly, dateTime, runsOf, typeWord } from "./format";
import { ResetRunsDialog } from "./ResetRunsDialog";

export function UserPanel({ userId }: { userId: string }) {
  const user = useAdminUser(userId);
  const setBlocked = useSetBlocked(userId);
  const [resetOpen, setResetOpen] = useState(false);
  const [blockOpen, setBlockOpen] = useState(false);

  if (user.isError) return <p className="text-sm text-destructive">Could not load this user.</p>;
  if (!user.data) return <Skeleton className="h-48 w-full" />;
  const u = user.data;

  const blockError =
    setBlocked.error instanceof ApiError && setBlocked.error.status === 409
      ? "Admin accounts cannot be blocked"
      : setBlocked.error
        ? "Could not change this account. Try again."
        : null;

  async function confirmBlock(block: boolean) {
    try {
      await setBlocked.mutateAsync(block);
      setBlockOpen(false);
    } catch {
      // Shown from blockError.
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="font-heading text-lg break-all">{u.email}</CardTitle>
        <p className="text-sm text-muted-foreground">
          Joined {dateOnly(u.joined_at)} · {runsOf(u.runs_used, u.runs_limit)} free runs used · ${u.free_spend_usd} spent
          {u.asked_for_more ? " · asked for more" : ""}
          {u.blocked ? " · " : ""}
          {u.blocked ? <Badge variant="destructive">Blocked</Badge> : null}
        </p>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {u.suggested_reset_runs !== null ? (
          <p className="rounded-lg bg-surface-muted px-3 py-2 text-sm text-foreground">
            <b className="font-semibold">Suggested:</b> some runs failed on our side, so a reset of up to {u.suggested_reset_runs} runs looks fair.
          </p>
        ) : null}
        <div className="flex flex-wrap gap-2">
          <Button className="min-h-11" disabled={u.runs_used === 0} onClick={() => setResetOpen(true)}>
            Reset free runs
          </Button>
          {u.blocked ? (
            <Button variant="outline" className="min-h-11" disabled={setBlocked.isPending} onClick={() => void setBlocked.mutateAsync(false).catch(() => undefined)}>
              Unblock user
            </Button>
          ) : (
            <Button variant="destructive" className="min-h-11" onClick={() => setBlockOpen(true)}>
              Block user
            </Button>
          )}
        </div>
        {u.blocked && blockError ? <p role="alert" className="text-sm text-destructive">{blockError}</p> : null}

        <section className="flex flex-col gap-2">
          <h3 className="font-medium text-foreground">Failed runs</h3>
          {u.failures.length === 0 ? (
            <p className="text-sm text-muted-foreground">No failed runs.</p>
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>When</TableHead>
                    <TableHead>Type</TableHead>
                    <TableHead>Why it failed</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {u.failures.map((f, i) => (
                    <TableRow key={`${f.when}-${i}`}>
                      <TableCell>{dateTime(f.when)}</TableCell>
                      <TableCell>{typeWord(f.type)}</TableCell>
                      <TableCell className="whitespace-normal">
                        {f.label}
                        {f.category === "did_not_finish" ? (
                          <>
                            {" "}
                            <Badge variant="outline">Never finished</Badge>
                          </>
                        ) : null}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </section>

        <section className="flex flex-col gap-2">
          <h3 className="font-medium text-foreground">History</h3>
          {u.history.length === 0 ? (
            <p className="text-sm text-muted-foreground">Nothing recorded yet.</p>
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>When</TableHead>
                    <TableHead>Who</TableHead>
                    <TableHead>What</TableHead>
                    <TableHead>Change</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {u.history.map((h, i) => (
                    <TableRow key={`${h.when}-${i}`}>
                      <TableCell>{dateTime(h.when)}</TableCell>
                      <TableCell className="min-w-56 break-all whitespace-normal">{h.actor_email}</TableCell>
                      <TableCell>{actionWord(h.action)}</TableCell>
                      <TableCell className="min-w-44 whitespace-normal">{changeWords(h.before, h.after).join(", ")}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
          <p className="text-sm text-muted-foreground">Every reset and block is recorded here with the time.</p>
        </section>
      </CardContent>

      {resetOpen ? (
        <ResetRunsDialog userId={userId} runsUsed={u.runs_used} suggested={u.suggested_reset_runs} open onOpenChange={setResetOpen} />
      ) : null}

      <AlertDialog
        open={blockOpen}
        onOpenChange={(next) => {
          setBlockOpen(next);
          if (!next) setBlocked.reset();
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Block {u.email}?</AlertDialogTitle>
            <AlertDialogDescription>They will not be able to start new runs. You can unblock them later.</AlertDialogDescription>
          </AlertDialogHeader>
          {blockError ? <p role="alert" className="text-sm text-destructive">{blockError}</p> : null}
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction variant="destructive" disabled={setBlocked.isPending} onClick={(e) => { e.preventDefault(); void confirmBlock(true); }}>
              Block
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  );
}
