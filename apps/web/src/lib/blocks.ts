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
