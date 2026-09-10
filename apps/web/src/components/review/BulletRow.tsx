"use client";

import type { Block } from "@/lib/api/queries";

export function BulletRow({
  path,
  text,
  sourceBlockId,
  block,
  selected,
  hasViolation,
  onSelect,
}: {
  path: string;
  text: string;
  sourceBlockId: string;
  block: Block | null;
  selected: boolean;
  hasViolation: boolean;
  onSelect: (path: string) => void;
}) {
  return (
    <li>
      <button
        type="button"
        onClick={() => onSelect(path)}
        aria-pressed={selected}
        className={`w-full rounded-md border px-3 py-2 text-left text-sm ${selected ? "border-accent bg-accent/5" : hasViolation ? "border-amber-300 bg-amber-50" : "border-transparent hover:border-border"}`}
      >
        <span>{text}</span>
        <span className="mt-1 block font-mono text-[11px] text-muted-foreground">
          {sourceBlockId}
          {block ? (block.verified ? " · verified" : " · unverified") : " · unknown block"}
        </span>
      </button>
    </li>
  );
}
