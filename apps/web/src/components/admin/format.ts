const TYPE_WORDS: Record<string, string> = { tailor_job: "Tailor" };

export function typeWord(type: string): string {
  if (TYPE_WORDS[type]) return TYPE_WORDS[type];
  const plain = type.replace(/_job$/, "").replace(/_/g, " ");
  return plain.charAt(0).toUpperCase() + plain.slice(1);
}

export function dateTime(iso: string): string {
  return new Date(iso).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

export function dateOnly(iso: string): string {
  return new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short" });
}

export function ago(iso: string, now: number = Date.now()): string {
  const mins = Math.max(0, Math.round((now - new Date(iso).getTime()) / 60000));
  if (mins < 60) return mins < 2 ? "just now" : `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

const ACTIONS: Record<string, string> = { reset_runs: "Reset free runs", block: "Blocked", unblock: "Unblocked" };
const FIELDS: Record<string, string> = { trial_runs_used: "Free runs used", blocked: "Blocked" };

export function actionWord(action: string): string {
  return ACTIONS[action] ?? action.replace(/_/g, " ");
}

function valueWord(v: unknown): string {
  if (v === true) return "yes";
  if (v === false) return "no";
  return String(v);
}

/** "Free runs used 3 → 1" for each field that appears in either side. */
export function changeWords(before: Record<string, unknown>, after: Record<string, unknown>): string[] {
  const keys = [...new Set([...Object.keys(before), ...Object.keys(after)])];
  return keys.map((k) => `${FIELDS[k] ?? k.replace(/_/g, " ")} ${valueWord(before[k])} → ${valueWord(after[k])}`);
}

export function runsOf(used: number, limit: number | null): string {
  return limit === null ? `${used}` : `${used} of ${limit}`;
}
