"use client";

import { useDroppable } from "@dnd-kit/core";
import type { ApplicationOut } from "@/lib/api/queries";
import { STATUS_LABEL, type ApplicationStatus } from "@/lib/status";
import { ApplicationCard } from "./ApplicationCard";

export function Column({ status, cards, onOpen }: { status: ApplicationStatus; cards: ApplicationOut[]; onOpen: (a: ApplicationOut) => void }) {
  const { setNodeRef, isOver } = useDroppable({ id: status });
  return (
    <section
      ref={setNodeRef}
      aria-label={`${STATUS_LABEL[status]} column`}
      className={`flex w-64 shrink-0 flex-col gap-2 rounded-md border p-2 ${isOver ? "border-accent bg-accent/5" : "border-border bg-muted/40"}`}
    >
      <header className="flex items-center justify-between px-1 py-1">
        <h2 className="font-sans text-sm font-medium">{STATUS_LABEL[status]}</h2>
        <span className="font-mono text-xs text-muted-foreground">{cards.length}</span>
      </header>
      {cards.map((a) => (
        <ApplicationCard key={a.id} application={a} onOpen={onOpen} />
      ))}
    </section>
  );
}
