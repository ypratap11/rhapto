"use client";

import { DndContext, KeyboardSensor, PointerSensor, useSensor, useSensors, type DragEndEvent } from "@dnd-kit/core";
import { useMemo, useState } from "react";
import { toast } from "sonner";
import { ApiErrorBanner } from "@/components/shell/ApiErrorBanner";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api/client";
import { useApplications, usePatchApplication, type ApplicationOut } from "@/lib/api/queries";
import { moveCard, normalizeColumns, type Columns } from "@/lib/board";
import { APPLICATION_STATUSES, type ApplicationStatus } from "@/lib/status";
import { ApplicationSheet } from "./ApplicationSheet";
import { Column } from "./Column";

export function Board() {
  const applications = useApplications();
  const patch = usePatchApplication();
  const [optimistic, setOptimistic] = useState<Columns | null>(null);
  const [selected, setSelected] = useState<ApplicationOut | null>(null);
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }), useSensor(KeyboardSensor));

  const derived = useMemo(() => (applications.data ? normalizeColumns(applications.data) : null), [applications.data]);
  const columns = optimistic ?? derived;

  async function onDragEnd(event: DragEndEvent) {
    if (!columns || !event.over) return;
    const id = String(event.active.id);
    const to = String(event.over.id) as ApplicationStatus;
    if (!APPLICATION_STATUSES.includes(to)) return;
    const next = moveCard(columns, id, to);
    if (next === columns) return;
    setOptimistic(next);
    try {
      await patch.mutateAsync({ id, body: { status: to } });
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Could not move the application");
    } finally {
      setOptimistic(null);
    }
  }

  if (applications.error) return <ApiErrorBanner error={applications.error} />;
  if (!columns) return <Skeleton className="h-64 w-full" />;

  return (
    <>
      <DndContext sensors={sensors} onDragEnd={onDragEnd}>
        <div className="flex gap-3 overflow-x-auto pb-4">
          {APPLICATION_STATUSES.map((status) => (
            <Column key={status} status={status} cards={columns[status]} onOpen={setSelected} />
          ))}
        </div>
      </DndContext>
      <ApplicationSheet application={selected} open={selected !== null} onOpenChange={(open) => !open && setSelected(null)} />
    </>
  );
}
