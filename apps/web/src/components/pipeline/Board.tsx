"use client";

import { DndContext, KeyboardSensor, PointerSensor, useSensor, useSensors, type DragEndEvent } from "@dnd-kit/core";
import { useMemo, useState } from "react";
import { toast } from "sonner";
import { ApiErrorBanner } from "@/components/shell/ApiErrorBanner";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api/client";
import { useApplications, usePatchApplication } from "@/lib/api/queries";
import { moveCard, normalizeColumns, type Columns } from "@/lib/board";
import { APPLICATION_STATUSES, type ApplicationStatus } from "@/lib/status";
import { ApplicationSheet } from "./ApplicationSheet";
import { Column } from "./Column";

function isApplicationStatus(value: string): value is ApplicationStatus {
  return (APPLICATION_STATUSES as readonly string[]).includes(value);
}

export function Board() {
  const applications = useApplications();
  const patch = usePatchApplication();
  const [optimistic, setOptimistic] = useState<Columns | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }), useSensor(KeyboardSensor));

  const derived = useMemo(() => (applications.data ? normalizeColumns(applications.data) : null), [applications.data]);
  const columns = optimistic ?? derived;
  const selectedApplication = selectedId ? (Object.values(columns ?? {}).flat().find((a) => a.id === selectedId) ?? null) : null;

  async function onDragEnd(event: DragEndEvent) {
    if (!columns || !event.over) return;
    const id = String(event.active.id);
    const toRaw = String(event.over.id);
    if (!isApplicationStatus(toRaw)) return;
    const to = toRaw;
    const next = moveCard(columns, id, to);
    if (next === columns) return;
    setOptimistic(next);
    try {
      await patch.mutateAsync({ id, body: { status: to } });
      // Wait for the server state to refresh before dropping the optimistic
      // override, so `derived` already reflects the move and there is no
      // flicker back to the pre-move snapshot.
      await applications.refetch();
      setOptimistic(null);
    } catch (e) {
      // Revert immediately on failure — do not wait on a refetch that may
      // still show the stale (pre-move) state anyway.
      setOptimistic(null);
      toast.error(e instanceof ApiError ? e.message : "Could not move the application");
    }
  }

  if (applications.error) return <ApiErrorBanner error={applications.error} />;
  if (!columns) return <Skeleton className="h-64 w-full" />;

  return (
    <>
      <DndContext sensors={sensors} onDragEnd={onDragEnd}>
        <div className="flex gap-3 overflow-x-auto pb-4">
          {APPLICATION_STATUSES.map((status) => (
            <Column key={status} status={status} cards={columns[status]} onOpen={(a) => setSelectedId(a.id)} />
          ))}
        </div>
      </DndContext>
      <ApplicationSheet
        application={selectedApplication}
        open={selectedId !== null && selectedApplication !== null}
        onOpenChange={(open) => !open && setSelectedId(null)}
      />
    </>
  );
}
