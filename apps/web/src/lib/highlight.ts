export type Segment = { text: string; hit: boolean };

function escapeRegex(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

export function highlightTerms(text: string, terms: string[]): Segment[] {
  const cleaned = Array.from(new Set(terms.map((t) => t.trim()).filter((t) => t.length > 0))).sort((a, b) => b.length - a.length);
  if (cleaned.length === 0 || text.length === 0) return [{ text, hit: false }];
  const pattern = new RegExp(`(?<![\\p{L}\\p{N}])(?:${cleaned.map(escapeRegex).join("|")})(?![\\p{L}\\p{N}])`, "giu");
  const segments: Segment[] = [];
  let last = 0;
  for (const match of text.matchAll(pattern)) {
    const start = match.index ?? 0;
    if (start > last) segments.push({ text: text.slice(last, start), hit: false });
    segments.push({ text: match[0], hit: true });
    last = start + match[0].length;
  }
  if (last < text.length) segments.push({ text: text.slice(last), hit: false });
  return segments;
}
