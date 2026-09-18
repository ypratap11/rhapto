import { useSyncExternalStore } from "react";

export const APPLY_OPENED_PREFIX = "rhapto.apply-opened.";

// Rhapto never submits (CLAUDE.md rule 1). It opens the employer's page in a new tab, and the only
// way to learn what happened there is to ask when the user comes back — so this module records
// "we sent you out for job X" and watches for the tab regaining focus.
let returned = false;
const listeners = new Set<() => void>();

function notify(): void {
  for (const listener of listeners) listener();
}

function onReturn(): void {
  if (typeof document === "undefined" || document.visibilityState === "visible") {
    returned = true;
    notify();
  }
}

function subscribe(onStoreChange: () => void): () => void {
  listeners.add(onStoreChange);
  if (listeners.size === 1) {
    window.addEventListener("focus", onReturn);
    document.addEventListener("visibilitychange", onReturn);
  }
  return () => {
    listeners.delete(onStoreChange);
    if (listeners.size === 0) {
      window.removeEventListener("focus", onReturn);
      document.removeEventListener("visibilitychange", onReturn);
    }
  };
}

export function markApplyOpened(jobId: string, now: Date = new Date()): void {
  try {
    localStorage.setItem(`${APPLY_OPENED_PREFIX}${jobId}`, now.toISOString());
  } catch {
    // Storage unavailable: the prompt just will not appear; nothing else breaks.
  }
  returned = false;
  notify();
}

export function applyOpenedAt(jobId: string): string | null {
  try {
    return localStorage.getItem(`${APPLY_OPENED_PREFIX}${jobId}`);
  } catch {
    return null;
  }
}

export function clearApplyOpened(jobId: string): void {
  try {
    localStorage.removeItem(`${APPLY_OPENED_PREFIX}${jobId}`);
  } catch {
    // as above
  }
  returned = false;
  notify();
}

/** True once the user has come back to this tab after opening the posting for `jobId`. */
export function useApplyPrompt(jobId: string): boolean {
  const opened = useSyncExternalStore(subscribe, () => applyOpenedAt(jobId) !== null, () => false);
  const back = useSyncExternalStore(subscribe, () => returned, () => false);
  return opened && back;
}
