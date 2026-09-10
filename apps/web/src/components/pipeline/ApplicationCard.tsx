"use client";

import { useDraggable } from "@dnd-kit/core";
import { CSS } from "@dnd-kit/utilities";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import type { ApplicationOut } from "@/lib/api/queries";
import { formatDate, formatRelative } from "@/lib/format";

export function ApplicationCard({ application, onOpen }: { application: ApplicationOut; onOpen: (a: ApplicationOut) => void }) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({ id: application.id });
  return (
    <div
      ref={setNodeRef}
      style={{ transform: CSS.Translate.toString(transform) }}
      className={`rounded-md border border-border bg-card p-3 text-sm shadow-sm ${isDragging ? "opacity-70" : ""}`}
      {...attributes}
      {...listeners}
      aria-roledescription="draggable application"
    >
      <p className="font-medium">{application.job.company ?? "Unknown company"}</p>
      <p className="text-muted-foreground">{application.job.title ?? "Untitled role"}</p>
      <p className="mt-1 text-xs text-muted-foreground">
        {application.applied_at ? `applied ${formatDate(application.applied_at)}` : `added ${formatRelative(application.created_at)}`}
      </p>
      <div className="mt-2 flex items-center justify-between">
        {application.package_id ? (
          <Link
            href={`/jobs/${application.job.id}/packages/${application.package_id}`}
            className="text-xs text-accent underline"
            onPointerDown={(e) => e.stopPropagation()}
          >
            Package
          </Link>
        ) : (
          <span />
        )}
        <Button size="sm" variant="ghost" onClick={() => onOpen(application)} onPointerDown={(e) => e.stopPropagation()}>
          Open
        </Button>
      </div>
    </div>
  );
}
