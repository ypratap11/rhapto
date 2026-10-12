/** Is this block missing a usable period?
 *
 * One definition, shared by `BlocksTab`'s "N need a period" chip and by whatever else asks. The API
 * counts the same condition (`period IS NULL OR btrim(period) = ''` in
 * `db/repositories/dashboard.py::checklist`), and the two must agree: the dashboard checklist row
 * deep-links into the tab, so a count that disagreed with the list underneath it would send the user
 * to a screen that showed nothing to fix.
 *
 * `!b.period` alone was the old inline test and it is nearly right — it does catch `""` — but it
 * misses a period of whitespace, which the API's `btrim` does catch. `resume_blocks.period` is
 * nullable free text, and nothing constrains a row written by an older import or by hand.
 */
export function isDateless(block: { period?: string | null }): boolean {
  return (block.period ?? "").trim() === "";
}

/** The blocks with no usable period, in the order given. */
export function datelessBlocks<T extends { period?: string | null }>(blocks: readonly T[]): T[] {
  return blocks.filter(isDateless);
}

function snippet(text: string | null | undefined, max: number): string {
  const flat = (text ?? "").replace(/\s+/g, " ").trim();
  return flat.length > max ? `${flat.slice(0, max).trimEnd()}…` : flat;
}

/**
 * A human name for one row of "Your experience", used in button labels, the delete confirmation and
 * toasts so the internal short name never leaks to the screen. Several achievements share one
 * employer and role, so the label adds the start of the item's own text to stay unique per row:
 * `org · role: text`, else the text alone, else the employer/role, else the short name.
 */
export function blockLabel(block: { id: string; org?: string | null; role?: string | null; content?: string | null }): string {
  const who = [block.org, block.role].filter(Boolean).join(" · ");
  const text = snippet(block.content, 40);
  if (who && text) return `${who}: ${text}`;
  return text || who || block.id;
}
