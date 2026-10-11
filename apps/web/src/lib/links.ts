/** The public repository ("Open source" in the footer). */
export const GITHUB_URL = "https://github.com/ypratap11/rhapto";

/** `raw` as an absolute http(s) URL, or null. Job links come from third-party feeds and from jobs
 * people paste, so they are untrusted: a `javascript:` or `data:` link in an href or `window.open`
 * would run script on our origin. Render or open a job link only through this. */
export function safeHttpUrl(raw: string | null | undefined): string | null {
  if (!raw) return null;
  try {
    const url = new URL(raw);
    return url.protocol === "https:" || url.protocol === "http:" ? url.toString() : null;
  } catch {
    return null;
  }
}
