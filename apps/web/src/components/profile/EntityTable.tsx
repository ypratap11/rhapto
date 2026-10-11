"use client";

import { Pencil, Trash2 } from "lucide-react";
import { useState } from "react";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";

export type ColumnDef<T> = { key: string; header: string; render: (row: T) => React.ReactNode };

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
      {/* A stacked card list, not a <table>: the editors open in a side sheet only ~520px wide (and the
        * screen is 375px on a phone), where a table of nowrap cells outgrew its box and pushed Edit and
        * Delete out of view. Cards wrap their content, so nothing here depends on the container width and
        * no horizontal scroller is needed. The first column is the row's title; the rest are labelled. */}
      <ul className="space-y-2">
        {rows.map((row) => {
          const [title, ...rest] = columns;
          return (
            <li key={getKey(row)} data-slot="entity-row" className="flex items-start gap-2 rounded-card border border-border bg-surface p-3 text-sm">
              <div className="min-w-0 flex-1 space-y-1.5">
                {title ? <div className="min-w-0 break-words">{title.render(row)}</div> : null}
                {rest.length > 0 ? (
                  <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs">
                    {rest.map((c) => (
                      <div key={c.key} className="flex min-w-0 max-w-full items-center gap-1.5">
                        <span className="shrink-0 text-muted-foreground">{c.header}</span>
                        <div className="min-w-0 break-words text-sm">{c.render(row)}</div>
                      </div>
                    ))}
                  </div>
                ) : null}
              </div>
              <div className="flex shrink-0 items-center">
                <Button variant="ghost" size="icon" className="max-md:min-h-11 max-md:min-w-11" aria-label={`Edit ${getLabel(row)}`} onClick={() => onEdit(row)}>
                  <Pencil className="size-4" aria-hidden />
                </Button>
                {onDelete ? (
                  <Button variant="ghost" size="icon" className="max-md:min-h-11 max-md:min-w-11" aria-label={`Delete ${getLabel(row)}`} onClick={() => setPending(row)}>
                    <Trash2 className="size-4" aria-hidden />
                  </Button>
                ) : null}
              </div>
            </li>
          );
        })}
      </ul>
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
