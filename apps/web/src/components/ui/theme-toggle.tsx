"use client";

import { Moon, Sun } from "lucide-react";
import { useSyncExternalStore } from "react";
import { Button } from "@/components/ui/button";

/** Read and written by the pre-hydration script in `app/layout.tsx`; keep the key in sync. */
export const THEME_STORAGE_KEY = "rhapto.theme";

// The theme lives on <html>, not in React state: the inline script in the root layout sets it
// before hydration. `useSyncExternalStore` reads that DOM state instead of copying it into an effect.
const listeners = new Set<() => void>();

function subscribe(onStoreChange: () => void): () => void {
  listeners.add(onStoreChange);
  return () => {
    listeners.delete(onStoreChange);
  };
}

function isDark(): boolean {
  return document.documentElement.classList.contains("dark");
}

function applyTheme(dark: boolean): void {
  document.documentElement.classList.toggle("dark", dark);
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, dark ? "dark" : "light");
  } catch {
    // Private mode or a blocked origin: the class still flips, the choice just is not remembered.
  }
  for (const listener of listeners) listener();
}

export function ThemeToggle({ className }: { className?: string }) {
  const dark = useSyncExternalStore(
    subscribe,
    isDark,
    () => false, // The server has no document; the inline script corrects the first client read.
  );
  return (
    <Button variant="ghost" size="icon-sm" aria-label="Toggle theme" aria-pressed={dark} className={className} onClick={() => applyTheme(!isDark())}>
      {dark ? <Moon aria-hidden="true" /> : <Sun aria-hidden="true" />}
    </Button>
  );
}

/** The same switch as a labelled row for the account menu and the phone sheet: the words name the
 * mode you will get, so a menu never shows a bare icon. */
export function ThemeMenuItem({ className }: { className?: string }) {
  const dark = useSyncExternalStore(subscribe, isDark, () => false);
  return (
    <button type="button" className={className} onClick={() => applyTheme(!isDark())}>
      {dark ? "Light mode" : "Dark mode"}
    </button>
  );
}
