"use client";

import { Check, Pencil, X } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import type { Block } from "@/lib/api/queries";

export function BulletRow({
  path,
  text,
  sourceBlockId,
  block,
  selected,
  hasViolation,
  onSelect,
  editable = false,
  onChange,
  onRemove,
}: {
  path: string;
  text: string;
  sourceBlockId: string;
  block: Block | null;
  selected: boolean;
  hasViolation: boolean;
  onSelect: (path: string) => void;
  editable?: boolean;
  onChange?: (path: string, text: string) => void;
  onRemove?: (path: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(text);

  function startEditing() {
    setDraft(text);
    setEditing(true);
  }

  function save() {
    const trimmed = draft.trim();
    if (trimmed) onChange?.(path, trimmed);
    setEditing(false);
  }

  function cancel() {
    setDraft(text);
    setEditing(false);
  }

  if (editable && editing) {
    return (
      <li className="space-y-1 rounded-md border border-accent bg-accent/5 p-2">
        <Textarea
          aria-label="Edit bullet"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          rows={3}
          autoFocus
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              save();
            }
            if (e.key === "Escape") {
              e.preventDefault();
              cancel();
            }
          }}
        />
        <div className="flex justify-end gap-1">
          <Button type="button" variant="ghost" size="icon-sm" aria-label="Cancel edit" onClick={cancel}>
            <X className="size-3.5" />
          </Button>
          <Button type="button" variant="ghost" size="icon-sm" aria-label="Save bullet" onClick={save}>
            <Check className="size-3.5" />
          </Button>
        </div>
      </li>
    );
  }

  return (
    <li>
      <div
        className={`flex items-start gap-1 rounded-md border px-3 py-2 text-sm ${selected ? "border-accent bg-accent/5" : hasViolation ? "border-fit-mid/40 bg-fit-mid-bg" : "border-transparent hover:border-border"}`}
      >
        <button type="button" onClick={() => onSelect(path)} onDoubleClick={editable ? startEditing : undefined} aria-pressed={selected} className="flex-1 text-left">
          <span>{text}</span>
          <span className="mt-1 block font-mono text-[11px] text-muted-foreground">
            {sourceBlockId}
            {block ? (block.verified ? " · verified" : " · unverified") : " · unknown block"}
          </span>
        </button>
        {editable ? (
          <div className="flex shrink-0 gap-1">
            <Button type="button" variant="ghost" size="icon-sm" aria-label="Edit bullet" onClick={startEditing}>
              <Pencil className="size-3.5" />
            </Button>
            <Button type="button" variant="ghost" size="icon-sm" aria-label="Remove bullet" onClick={() => onRemove?.(path)}>
              <X className="size-3.5" />
            </Button>
          </div>
        ) : null}
      </div>
    </li>
  );
}
