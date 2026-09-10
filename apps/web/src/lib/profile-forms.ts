import type { Block } from "@/lib/api/queries";

export const KNOWN_RULES = ["no-unverified-metrics", "no-invented-entities", "date-consistency", "attribution", "visibility-context"] as const;
export const BLOCK_TYPES = ["achievement", "role", "project", "skill", "credential"] as const;
export const ID_RE = /^[a-z0-9][a-z0-9-]*$/;
const PERIOD_RE =
  /^(?:(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+)?\d{4}(?:\s*(?:-|–|—|to)\s*(?:(?:[A-Z][a-z]+\.?\s+)?\d{4}|[Pp]resent|[Cc]urrent|[Nn]ow))?$/;

export function splitList(text: string): string[] {
  return Array.from(new Set(text.split(/[,\n]/).map((s) => s.trim()).filter(Boolean)));
}

export function joinList(items: string[]): string {
  return items.join(", ");
}

export type BlockForm = {
  id: string;
  type: string;
  org: string;
  role: string;
  period: string;
  verified: boolean;
  metric: string;
  content: string;
  tags: string;
  attribution: string;
  concurrent: boolean;
  exclude_when: string;
};

export const emptyBlockForm: BlockForm = { id: "", type: "achievement", org: "", role: "", period: "", verified: false, metric: "", content: "", tags: "", attribution: "", concurrent: false, exclude_when: "" };

export function blockToForm(block: Block): BlockForm {
  return {
    id: block.id,
    type: block.type,
    org: block.org ?? "",
    role: block.role ?? "",
    period: block.period ?? "",
    verified: block.verified,
    metric: block.metric ?? "",
    content: block.content,
    tags: joinList(block.tags),
    attribution: block.attribution ?? "",
    concurrent: block.concurrent,
    exclude_when: joinList(block.visibility?.exclude_when ?? []),
  };
}

const orNull = (s: string) => (s.trim() ? s.trim() : null);

export function formToBlock(form: BlockForm): Block {
  const exclude = splitList(form.exclude_when);
  return {
    id: form.id.trim(),
    type: form.type as Block["type"],
    org: orNull(form.org),
    role: orNull(form.role),
    period: orNull(form.period),
    verified: form.verified,
    metric: orNull(form.metric),
    content: form.content.trim(),
    tags: splitList(form.tags),
    attribution: orNull(form.attribution),
    concurrent: form.concurrent,
    visibility: exclude.length ? { exclude_when: exclude } : null,
  };
}

export function validateBlockForm(form: BlockForm): Record<string, string> {
  const errors: Record<string, string> = {};
  if (!ID_RE.test(form.id.trim())) errors.id = "Use lowercase letters, digits, and hyphens, starting with a letter or digit.";
  if (!(BLOCK_TYPES as readonly string[]).includes(form.type)) errors.type = "Pick a type.";
  if (!form.content.trim()) errors.content = "Content is required.";
  if (form.period.trim() && !PERIOD_RE.test(form.period.trim())) errors.period = "Use YYYY, YYYY-YYYY, Mon YYYY - Present, and so on.";
  return errors;
}

export function parseJsonObject(text: string): { value: Record<string, unknown> | null; error: string | null } {
  if (!text.trim()) return { value: {}, error: null };
  try {
    const parsed: unknown = JSON.parse(text);
    if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) return { value: null, error: "Config must be a JSON object." };
    return { value: parsed as Record<string, unknown>, error: null };
  } catch {
    return { value: null, error: "Invalid JSON." };
  }
}
