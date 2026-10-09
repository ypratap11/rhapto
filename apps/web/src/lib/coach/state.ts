/** Where the coach starts. Server state decides; the URL's `step` is only a hint, capped at the
 * furthest step server state allows (architect I5c). Pure: no React, no storage. */
export type ServerState = {
  /** `?task=<id>` from the URL: a tailor run to re-attach to. */
  taskId: string | null;
  hasDocument: boolean;
  trackIds: string[];
  /** The coach's last confirmed track for this user (localStorage). The API's Track has no updated_at. */
  confirmedTrackId: string | null;
};

export type StartStep = 1 | 2 | 3 | 4 | 5;
export type Start = { step: StartStep; trackId: string | null };

function trackFor(server: ServerState): string | null {
  if (server.confirmedTrackId && server.trackIds.includes(server.confirmedTrackId)) return server.confirmedTrackId;
  return server.trackIds[0] ?? null;
}

function furthest(server: ServerState): 1 | 2 | 4 | 5 {
  if (server.taskId) return 5;
  if (!server.hasDocument) return 1;
  return server.trackIds.length > 0 ? 4 : 2;
}

export function deriveStartStep(server: ServerState, hint: number | null = null): Start {
  const max = furthest(server);
  const step = (hint !== null && hint >= 1 && hint < max ? hint : max) as StartStep;
  return { step, trackId: step >= 3 || (step === 2 && server.trackIds.length > 0) ? trackFor(server) : null };
}

/** `?step=` -> an integer 1..5, or null. */
export function parseStepHint(raw: string | null): number | null {
  if (raw === null || !/^[1-5]$/.test(raw)) return null;
  return Number(raw);
}

/** The job a tailor task was started for, from the request stored on the task row. */
export function jobIdFromTask(task: { progress?: Record<string, unknown> } | undefined): string | null {
  const request = task?.progress?.request;
  if (typeof request !== "object" || request === null) return null;
  const id = (request as Record<string, unknown>).job_id;
  return typeof id === "string" ? id : null;
}
