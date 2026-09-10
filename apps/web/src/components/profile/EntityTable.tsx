"use client";

import { Pencil, Trash2 } from "lucide-react";
import { useState } from "react";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

export type ColumnDef<T> = { key: string; header: string; render: (row: T) => React.ReactNode; className?: string };

export function EntityTable<T>({
  columns,
  rows,
  getKey,
  getLabel,
  onEdit,
  onDelete,
  emptyText,
}: {
  columns: ColumnDef<T>[];
  rows: T[];
  getKey: (row: T) => string;
  getLabel: (row: T) => string;
  onEdit: (row: T) => void;
  onDelete?: (row: T) => Promise<void>;
  emptyText: string;
}) {
  const [pending, setPending] = useState<T | null>(null);
  if (rows.length === 0) return <p className="py-6 text-sm text-muted-foreground">{emptyText}</p>;
  return (
    <>
      <Table>
        <TableHeader>
          <TableRow>
            {columns.map((c) => (
              <TableHead key={c.key} className={c.className}>
                {c.header}
              </TableHead>
            ))}
            <TableHead className="w-24" />
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row) => (
            <TableRow key={getKey(row)}>
              {columns.map((c) => (
                <TableCell key={c.key} className={c.className}>
                  {c.render(row)}
                </TableCell>
              ))}
              <TableCell className="text-right">
                <Button variant="ghost" size="icon" aria-label={`Edit ${getLabel(row)}`} onClick={() => onEdit(row)}>
                  <Pencil className="size-4" aria-hidden />
                </Button>
                {onDelete ? (
                  <Button variant="ghost" size="icon" aria-label={`Delete ${getLabel(row)}`} onClick={() => setPending(row)}>
                    <Trash2 className="size-4" aria-hidden />
                  </Button>
                ) : null}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      <AlertDialog open={pending !== null} onOpenChange={(o) => !o && setPending(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete {pending ? getLabel(pending) : ""}?</AlertDialogTitle>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={async () => {
                try {
                  if (pending && onDelete) await onDelete(pending);
                } catch {
                  // The caller's onDelete is responsible for surfacing the error (e.g. a toast);
                  // this catch only guarantees the confirm dialog always closes.
                } finally {
                  setPending(null);
                }
              }}
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
