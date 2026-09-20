const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export function formatDate(iso: string): string {
  const d = new Date(iso);
  return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()] ?? ""} ${d.getUTCFullYear()}`;
}

export function formatRelative(iso: string, now: Date = new Date()): string {
  const seconds = Math.max(0, Math.round((now.getTime() - new Date(iso).getTime()) / 1000));
  if (seconds < 60) return "just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

export function truncate(text: string, max: number): string {
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

/** A token count with thousands separators (12,345), never abbreviated: this is a usage figure
 * someone may want to reconcile against a bill, not a display headline. */
export function formatTokens(n: number): string {
  return new Intl.NumberFormat("en-US").format(n);
}

/** An estimated USD spend. A non-zero amount that would round to $0.00 (a handful of cache-read
 * tokens, say) shows as "<$0.01" instead -- rounding it to zero would read as free, which it isn't. */
export function formatCostUsd(usd: number): string {
  if (usd > 0 && usd < 0.01) return "<$0.01";
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(usd);
}
