export type ParsedPath =
  | { kind: "summary"; index: number }
  | { kind: "entry"; section: number; entry: number }
  | { kind: "bullet"; section: number; entry: number; bullet: number }
  | { kind: "field"; section: number; entry: number; field: string }
  | { kind: "cover_note" }
  | { kind: "unknown"; raw: string };

export const summaryPath = (i: number) => `summary[${i}]`;
export const entryPath = (s: number, e: number) => `sections[${s}].entries[${e}]`;
export const bulletPath = (s: number, e: number, b: number) => `${entryPath(s, e)}.bullets[${b}]`;
export const fieldPath = (s: number, e: number, field: string) => `${entryPath(s, e)}.${field}`;

const SUMMARY = /^summary\[(\d+)\]$/;
const ENTRY = /^sections\[(\d+)\]\.entries\[(\d+)\](?:\.(bullets\[(\d+)\]|([a-z_]+)))?$/;

export function parsePath(path: string): ParsedPath {
  if (path === "cover_note") return { kind: "cover_note" };
  const s = SUMMARY.exec(path);
  if (s) return { kind: "summary", index: Number(s[1]) };
  const e = ENTRY.exec(path);
  if (!e) return { kind: "unknown", raw: path };
  const section = Number(e[1]);
  const entry = Number(e[2]);
  if (e[4] !== undefined) return { kind: "bullet", section, entry, bullet: Number(e[4]) };
  if (e[5] !== undefined) return { kind: "field", section, entry, field: e[5] };
  return { kind: "entry", section, entry };
}
