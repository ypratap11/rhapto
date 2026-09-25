"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/ui/StatusBadge";
import type { Block } from "@/lib/api/queries";

/**
 * The block's sentence, with its metric called out as a chip rather than spliced into the prose —
 * the same `StatusBadge` chip used everywhere else (no new chip shape), so the number being asked
 * about reads as unmistakably separate from the surrounding claim.
 */
function BlockCard({ block }: { block: Block }) {
  return (
    <div className="space-y-2 rounded-md border border-border bg-surface p-4">
      <p className="text-sm">{block.content}</p>
      {block.metric ? (
        <p className="text-sm text-muted-foreground">
          Claims <StatusBadge tone="primary">{block.metric}</StatusBadge>
        </p>
      ) : null}
      <p className="text-sm font-medium text-foreground">Is this accurate and defensible?</p>
    </div>
  );
}

/**
 * Spec §6's guided metric confirmation: the moment an imported, unverified block's number turns
 * from prose Rhapto will strip ("many departments") into a citable figure ("15+ departments and
 * 10+ cross-functional teams") — by the user asserting it themselves, one block at a time. Walks
 * only the blocks that carry a `metric`; every other imported block was already saved unverified
 * in the review step and needs no attention here.
 */
export function ConfirmMetrics({
  blocks,
  onConfirm,
  onSkip,
  onDone,
}: {
  blocks: Block[];
  onConfirm: (id: string) => void;
  onSkip: (id: string) => void;
  onDone: () => void;
}) {
  const [index, setIndex] = useState(0);
  const current = blocks[index];

  function advance() {
    if (index + 1 >= blocks.length) {
      onDone();
    } else {
      setIndex(index + 1);
    }
  }

  if (!current) {
    onDone();
    return null;
  }

  return (
    <div className="space-y-4">
      <p className="text-xs text-muted-foreground">
        {index + 1} of {blocks.length}
      </p>
      <BlockCard block={current} />
      <div className="flex justify-end gap-2">
        <Button
          variant="outline"
          onClick={() => {
            onSkip(current.id);
            advance();
          }}
        >
          Skip
        </Button>
        <Button
          onClick={() => {
            onConfirm(current.id);
            advance();
          }}
        >
          Yes, it&rsquo;s accurate
        </Button>
      </div>
      <p className="text-xs text-muted-foreground">
        Unconfirmed numbers are removed from generated resumes — the claim stays, the figure goes.
      </p>
    </div>
  );
}
