import { useSyncExternalStore } from "react";

// Tiny external store tracking which jobs currently have a tailoring task in
// flight, so the step bar can highlight "Tailor" without threading state
// through every route that renders it.
const active = new Set<string>();
const listeners = new Set<() => void>();

function emit(): void {
  for (const listener of listeners) listener();
}

export function startTailoring(jobId: string): void {
  active.add(jobId);
  emit();
}

export function stopTailoring(jobId: string): void {
  active.delete(jobId);
  emit();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function getSnapshot(): number {
  return active.size;
}

function getServerSnapshot(): number {
  return 0;
}

export function useTailoringCount(): number {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}
