import type { ApplicationOut, BoardOut } from "@/lib/api/queries";
import { APPLICATION_STATUSES, type ApplicationStatus } from "./status";

export type Columns = Record<ApplicationStatus, ApplicationOut[]>;

export function normalizeColumns(board: BoardOut): Columns {
  const columns = {} as Columns;
  for (const status of APPLICATION_STATUSES) columns[status] = [...((board.columns as Record<string, ApplicationOut[]>)[status] ?? [])];
  return columns;
}

export function findColumn(columns: Columns, applicationId: string): ApplicationStatus | null {
  for (const status of APPLICATION_STATUSES) if (columns[status].some((a) => a.id === applicationId)) return status;
  return null;
}

export function moveCard(columns: Columns, applicationId: string, to: ApplicationStatus): Columns {
  const from = findColumn(columns, applicationId);
  if (from === null || from === to) return columns;
  const card = columns[from].find((a) => a.id === applicationId)!;
  return {
    ...columns,
    [from]: columns[from].filter((a) => a.id !== applicationId),
    [to]: [{ ...card, status: to }, ...columns[to]],
  };
}
