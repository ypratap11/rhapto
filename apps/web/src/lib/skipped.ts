import { useSyncExternalStore } from "react";

const KEY = "rhapto.skipped";
const EVENT = "rhapto-skipped";
const EMPTY: string[] = [];

export function readSkipped(): string[] {
  try {
    const raw = localStorage.getItem(KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed.filter((x): x is string => typeof x === "string") : [];
  } catch {
    return [];
  }
}

function write(ids: string[]): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(ids));
  } catch {
    // storage unavailable: the skip simply does not persist
  }
  window.dispatchEvent(new Event(EVENT));
}

export function skipJob(id: string): string[] {
  const current = readSkipped();
  const next = current.includes(id) ? current : [...current, id];
  write(next);
  return next;
}

export function unskipAll(): void {
  write([]);
}

let cache: string[] = EMPTY;
let cacheRaw: string | null = null;
function snapshot(): string[] {
  let raw: string | null = null;
  try {
    raw = localStorage.getItem(KEY);
  } catch {
    raw = null;
  }
  if (raw !== cacheRaw) {
    cacheRaw = raw;
    cache = readSkipped();
  }
  return cache;
}

export function useSkipped(): string[] {
  return useSyncExternalStore(
    (cb) => {
      window.addEventListener(EVENT, cb);
      window.addEventListener("storage", cb);
      return () => {
        window.removeEventListener(EVENT, cb);
        window.removeEventListener("storage", cb);
      };
    },
    snapshot,
    () => EMPTY,
  );
}
